#!/bin/bash
#
# Deploy YT News Generator to AWS EC2
# Usage: ./deploy-ec2.sh [--key-path PATH_TO_PEM] [--region REGION]
#

set -e

# ==========================================
# Configuration
# ==========================================

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
INSTANCE_TYPE="t4g.nano"
APP_NAME="yt-news-generator"
KEY_PATH="credentials/yt-news-generator-key.pem"
KEY_NAME="yt-news-generator-key"

# Ubuntu 22.04 LTS ARM64 AMIs (for t4g Graviton instances)
get_ami_for_region() {
  case "$1" in
    us-east-1) echo "ami-0a0c8eebcdd6dcbd0" ;;
    us-east-2) echo "ami-0b8b44ec9a8f90422" ;;
    us-west-1) echo "ami-0036b4598ccd42565" ;;
    us-west-2) echo "ami-0ca05c6eaa5f73eba" ;;
    eu-west-1) echo "ami-0b9fd8b55a6e3c9d5" ;;
    eu-central-1) echo "ami-0e04bcbe83a83792e" ;;
    *) echo "" ;;
  esac
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --key-path)
      KEY_PATH="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: ./deploy-ec2.sh [--key-path PATH_TO_PEM] [--region REGION]"
      exit 1
      ;;
  esac
done

AMI_ID=$(get_ami_for_region "$REGION")
if [ -z "$AMI_ID" ]; then
  echo "ERROR: No AMI configured for region $REGION"
  echo "Supported regions: us-east-1, us-east-2, us-west-1, us-west-2, eu-west-1, eu-central-1"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "Deploying $APP_NAME to AWS EC2"
echo "========================================"
echo "Region: $REGION"
echo "Instance type: $INSTANCE_TYPE"
echo "Key: $KEY_PATH"
echo ""

# ==========================================
# Check prerequisites
# ==========================================

if ! command -v aws &> /dev/null; then
  echo "ERROR: AWS CLI not installed"
  exit 1
fi

if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
  echo "ERROR: AWS credentials not set"
  echo "Set environment variables:"
  echo "  export AWS_ACCESS_KEY_ID=your_access_key"
  echo "  export AWS_SECRET_ACCESS_KEY=your_secret_key"
  exit 1
fi

if ! aws sts get-caller-identity &> /dev/null; then
  echo "ERROR: AWS credentials invalid"
  exit 1
fi

if [ ! -f "$KEY_PATH" ]; then
  echo "ERROR: Key file not found: $KEY_PATH"
  exit 1
fi

echo "AWS credentials OK"

# ==========================================
# Create/get security group
# ==========================================

SG_NAME="${APP_NAME}-sg"
SG_ID=$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --filters "Name=group-name,Values=$SG_NAME" \
  --query 'SecurityGroups[0].GroupId' \
  --output text 2>/dev/null || echo "None")

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  echo "Creating security group..."
  VPC_ID=$(aws ec2 describe-vpcs --region "$REGION" --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text)
  SG_ID=$(aws ec2 create-security-group --region "$REGION" --group-name "$SG_NAME" --description "YT News Generator" --vpc-id "$VPC_ID" --query 'GroupId' --output text)
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" --protocol tcp --port 22 --cidr 0.0.0.0/0
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" --protocol tcp --port 8000 --cidr 0.0.0.0/0
  echo "Security group created: $SG_ID"
else
  echo "Using security group: $SG_ID"
fi

# ==========================================
# Launch instance
# ==========================================

echo ""
echo "Launching EC2 instance..."

INSTANCE_ID=$(aws ec2 run-instances \
  --region "$REGION" \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$APP_NAME}]" \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "Instance: $INSTANCE_ID"
echo "Waiting for instance to be running..."

aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"

PUBLIC_IP=$(aws ec2 describe-instances \
  --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

echo "Public IP: $PUBLIC_IP"

# ==========================================
# Wait for SSH to be ready
# ==========================================

echo ""
echo "Waiting for SSH to be ready..."
for i in {1..30}; do
  if ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes ubuntu@"$PUBLIC_IP" "echo ready" 2>/dev/null; then
    echo "SSH ready!"
    break
  fi
  echo "  Attempt $i/30..."
  sleep 5
done

# ==========================================
# Setup server via SSH
# ==========================================

echo ""
echo "Installing dependencies on server..."

ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no ubuntu@"$PUBLIC_IP" << 'REMOTE_SCRIPT'
set -e

# Update and install base packages
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv git curl

# Remove conflicting Node.js packages and install Node 18
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get purge -y nodejs libnode72 libnode-dev 2>/dev/null || true
sudo apt-get autoremove -y
sudo apt-get install -y nodejs

echo "Node version: $(node --version)"
echo "npm version: $(npm --version)"
REMOTE_SCRIPT

# ==========================================
# Copy project files
# ==========================================

echo ""
echo "Copying project files..."

rsync -avz --progress \
  --exclude 'node_modules' \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude '.git' \
  --exclude 'credentials' \
  --exclude '*.pem' \
  -e "ssh -i $KEY_PATH -o StrictHostKeyChecking=no" \
  "$SCRIPT_DIR/" ubuntu@"$PUBLIC_IP":/home/ubuntu/yt-news-generator/

# ==========================================
# Setup Python environment and start server
# ==========================================

echo ""
echo "Setting up Python environment..."

ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no ubuntu@"$PUBLIC_IP" << 'REMOTE_SCRIPT'
set -e
cd /home/ubuntu/yt-news-generator

# Create Python venv and install requirements
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r webapp/backend/requirements.txt

# Create .env if not exists
if [ ! -f .env ]; then
  cat > .env << 'EOF'
export OPENAI_API_KEY=your_openai_key
export ELEVENLABS_API_KEY=your_elevenlabs_key
export PERPLEXITY_API_KEY=your_perplexity_key
export AUTH_PASSWORD=admin123
export HOST=0.0.0.0
export PORT=8000
EOF
  echo "Created .env template - update with your API keys"
fi

# Start the webapp
source .env
nohup python -m uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000 > /tmp/webapp.log 2>&1 &
sleep 2

if pgrep -f uvicorn > /dev/null; then
  echo "Webapp started successfully!"
else
  echo "ERROR: Webapp failed to start. Check /tmp/webapp.log"
  exit 1
fi
REMOTE_SCRIPT

# ==========================================
# Done
# ==========================================

echo ""
echo "========================================"
echo "DEPLOYMENT COMPLETE!"
echo "========================================"
echo ""
echo "Instance ID: $INSTANCE_ID"
echo "Public IP:   $PUBLIC_IP"
echo "Region:      $REGION"
echo ""
echo "Webapp: http://${PUBLIC_IP}:8000"
echo "Password: admin123"
echo ""
echo "SSH: ssh -i $KEY_PATH ubuntu@${PUBLIC_IP}"
echo ""
echo "To update API keys:"
echo "  ssh -i $KEY_PATH ubuntu@${PUBLIC_IP}"
echo "  nano /home/ubuntu/yt-news-generator/.env"
echo "  pkill uvicorn && cd /home/ubuntu/yt-news-generator && source .env && source venv/bin/activate && nohup python -m uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000 > /tmp/webapp.log 2>&1 &"
echo ""
