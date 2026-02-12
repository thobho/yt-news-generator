import { Config } from "@remotion/cli/config";
import os from "os";

// Image format for frames
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);

// Parallel rendering - use all available cores (adapts to machine)
const cpuCount = os.cpus().length;
Config.setConcurrency(Math.max(1, cpuCount));

// Video codec settings optimized for YouTube
Config.setCodec("h264");
Config.setPixelFormat("yuv420p");

// Quality setting (0-51, lower = better quality, 18-23 is visually lossless)
Config.setCrf(18);
