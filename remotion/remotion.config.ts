import { Config } from "@remotion/cli/config";

// Image format for frames
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);

// Parallel rendering - process multiple frames concurrently
Config.setConcurrency(8);

// Video codec settings optimized for YouTube
Config.setCodec("h264");
Config.setPixelFormat("yuv420p");

// Quality setting (0-51, lower = better quality, 18-23 is visually lossless)
Config.setCrf(18);
