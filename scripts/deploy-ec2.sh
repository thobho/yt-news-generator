#!/bin/bash
#
# Deploy YT News Generator to AWS EC2
# - Creates EC2 instance with IAM role for S3
# - Installs all system dependencies
# - Copies all credentials
# - Sets up swap for low-memory instances
# - Installs Python and NPM dependencies
# Usage: ./deploy-ec2.sh [--key-path PATH_TO_PEM] [--region REGION]
#

set -e

# ==========================================
# Configuration
# ==========================================

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
INSTANCE_TYPE="t4g.micro"
APP_NAME="yt-news-generator"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
KEY_PATH="$PROJECT_ROOT/credentials/yt-news-generator-key.pem"
KEY_NAME="yt-news-generator-key"
IAM_ROLE_NAME="yt-news-generator-ec2-role"
INSTANCE_PROFILE_NAME="yt-news-generator-ec2-profile"
S3_BUCKET="yt-news-generator"

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
# Create/get IAM role for S3 access
# ==========================================

echo ""
echo "Setting up IAM role for S3 access..."

if ! aws iam get-role --role-name "$IAM_ROLE_NAME" &>/dev/null; then
  echo "Creating IAM role..."
  aws iam create-role \
    --role-name "$IAM_ROLE_NAME" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Principal": {"Service": "ec2.amazonaws.com"},
          "Action": "sts:AssumeRole"
        }
      ]
    }' > /dev/null

  aws iam put-role-policy \
    --role-name "$IAM_ROLE_NAME" \
    --policy-name "${APP_NAME}-s3-access" \
    --policy-document "{
      \"Version\": \"2012-10-17\",
      \"Statement\": [
        {
          \"Effect\": \"Allow\",
          \"Action\": [\"s3:GetObject\", \"s3:PutObject\", \"s3:DeleteObject\", \"s3:ListBucket\"],
          \"Resource\": [\"arn:aws:s3:::${S3_BUCKET}\", \"arn:aws:s3:::${S3_BUCKET}/*\"]
        }
      ]
    }"
  echo "IAM role created: $IAM_ROLE_NAME"
else
  echo "Using existing IAM role: $IAM_ROLE_NAME"
fi

if ! aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" &>/dev/null; then
  echo "Creating instance profile..."
  aws iam create-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" > /dev/null
  aws iam add-role-to-instance-profile \
    --instance-profile-name "$INSTANCE_PROFILE_NAME" \
    --role-name "$IAM_ROLE_NAME"
  sleep 10
  echo "Instance profile created: $INSTANCE_PROFILE_NAME"
else
  echo "Using existing instance profile: $INSTANCE_PROFILE_NAME"
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
  --iam-instance-profile "Name=$INSTANCE_PROFILE_NAME" \
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
# Install system dependencies and setup swap
# ==========================================

echo ""
echo "Installing system dependencies..."

ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no ubuntu@"$PUBLIC_IP" << 'REMOTE_SCRIPT'
set -e

# Update and install base packages
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y python3-pip python3-venv git curl ffmpeg

# Install Chrome dependencies for Remotion
sudo apt-get install -y \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libdrm2 \
  libxkbcommon0 \
  libxcomposite1 \
  libxdamage1 \
  libxfixes3 \
  libxrandr2 \
  libgbm1 \
  libasound2 \
  libpango-1.0-0 \
  libcairo2 \
  libnss3 \
  libnspr4 \
  libx11-xcb1

# Install Node.js 18
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get purge -y nodejs libnode72 libnode-dev 2>/dev/null || true
sudo apt-get autoremove -y
sudo apt-get install -y nodejs

echo "Node version: $(node --version)"
echo "npm version: $(npm --version)"

# ---- Setup swap for instances with < 2GB RAM ----
TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
if [ "$TOTAL_MEM" -lt 2048 ]; then
  echo "Low memory detected (${TOTAL_MEM}MB). Setting up 2GB swap..."
  if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "Swap added!"
  else
    sudo swapon /swapfile 2>/dev/null || true
    echo "Swap already exists"
  fi
fi
echo "Memory: $(free -m | awk '/^Mem:/{print $2}')MB RAM, $(free -m | awk '/^Swap:/{print $2}')MB swap"
REMOTE_SCRIPT

# ==========================================
# Build frontend locally
# ==========================================

echo ""
echo "Building frontend locally..."

cd "$PROJECT_ROOT/webapp/frontend"

if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies..."
  npm install
fi

npm run build

rm -rf "$PROJECT_ROOT/webapp/backend/static"
cp -r dist "$PROJECT_ROOT/webapp/backend/static"
echo "Frontend built!"

cd "$PROJECT_ROOT"

# ==========================================
# Copy all credentials
# ==========================================

echo ""
echo "Copying credentials..."

# Create credentials directory
ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no ubuntu@"$PUBLIC_IP" \
  "mkdir -p /home/ubuntu/yt-news-generator/credentials"

# Copy env.production as .env
if [ -f "$PROJECT_ROOT/credentials/env.production" ]; then
  scp -i "$KEY_PATH" -o StrictHostKeyChecking=no \
    "$PROJECT_ROOT/credentials/env.production" \
    ubuntu@"$PUBLIC_IP":/home/ubuntu/yt-news-generator/.env
  echo "  - env.production -> .env"
fi

# Copy YouTube OAuth credentials
if [ -f "$PROJECT_ROOT/credentials/client_secrets.json" ]; then
  scp -i "$KEY_PATH" -o StrictHostKeyChecking=no \
    "$PROJECT_ROOT/credentials/client_secrets.json" \
    ubuntu@"$PUBLIC_IP":/home/ubuntu/yt-news-generator/credentials/
  echo "  - client_secrets.json"
fi

if [ -f "$PROJECT_ROOT/credentials/token.json" ]; then
  scp -i "$KEY_PATH" -o StrictHostKeyChecking=no \
    "$PROJECT_ROOT/credentials/token.json" \
    ubuntu@"$PUBLIC_IP":/home/ubuntu/yt-news-generator/credentials/
  echo "  - token.json"
fi

echo "Credentials copied!"

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
  --exclude 'output' \
  --exclude 'storage' \
  -e "ssh -i $KEY_PATH -o StrictHostKeyChecking=no" \
  "$PROJECT_ROOT/" ubuntu@"$PUBLIC_IP":/home/ubuntu/yt-news-generator/

# ==========================================
# Install Python/NPM dependencies and start server
# ==========================================

echo ""
echo "Setting up Python environment and dependencies..."

ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no ubuntu@"$PUBLIC_IP" << 'REMOTE_SCRIPT'
set -e
cd /home/ubuntu/yt-news-generator

# Create Python venv and install all requirements
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r webapp/backend/requirements.txt
pip install boto3 elevenlabs

# Install Remotion NPM dependencies
echo ""
echo "Installing Remotion dependencies..."
cd remotion
npm install
cd ..

# Create default .env if none exists
if [ ! -f .env ]; then
  cat > .env << 'EOF'
export OPENAI_API_KEY=your_openai_key
export ELEVENLABS_API_KEY=your_elevenlabs_key
export PERPLEXITY_API_KEY=your_perplexity_key
export AUTH_PASSWORD=admin123
export HOST=0.0.0.0
export PORT=8000

# S3 Storage (uses IAM role for credentials)
export STORAGE_BACKEND=s3
export S3_BUCKET=yt-news-generator
export S3_REGION=us-east-1
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
  tail -20 /tmp/webapp.log
  exit 1
fi
REMOTE_SCRIPT

# ==========================================
# Update sync script with new IP
# ==========================================

sed -i.bak "s/PUBLIC_IP=\"\${1:-[^}]*}\"/PUBLIC_IP=\"\${1:-${PUBLIC_IP}}\"/" "$SCRIPT_DIR/sync-ec2.sh"
rm -f "$SCRIPT_DIR/sync-ec2.sh.bak"

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
echo ""
echo "SSH: ssh -i $KEY_PATH ubuntu@${PUBLIC_IP}"
echo ""
