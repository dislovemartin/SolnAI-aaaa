#!/usr/bin/env python3
"""
GPU Monitoring Agent for Chimera
Collects GPU metrics and exposes them for Prometheus scraping
"""
import time
import os
import socket
import threading
from flask import Flask, Response
import prometheus_client
from prometheus_client import Gauge, Counter, Histogram
import pynvml
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("gpu-monitor")

# Initialize Flask app for metrics endpoint
app = Flask(__name__)

# Initialize NVML
try:
    pynvml.nvmlInit()
    logger.info("NVML initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize NVML: {e}")
    raise

# Get hostname for labels
HOSTNAME = socket.gethostname()
NODE_NAME = os.environ.get("NODE_NAME", HOSTNAME)

# Prometheus metrics
GPU_UTIL = Gauge('chimera_gpu_utilization_percent', 
                'GPU Utilization Percentage', 
                ['gpu_id', 'gpu_type', 'node'])

GPU_MEMORY_USED = Gauge('chimera_gpu_memory_used_bytes', 
                       'GPU Memory Used in Bytes', 
                       ['gpu_id', 'gpu_type', 'node'])

GPU_MEMORY_TOTAL = Gauge('chimera_gpu_memory_total_bytes', 
                         'GPU Total Memory in Bytes', 
                         ['gpu_id', 'gpu_type', 'node'])

GPU_POWER_USAGE = Gauge('chimera_gpu_power_usage_watts', 
                        'GPU Power Usage in Watts', 
                        ['gpu_id', 'gpu_type', 'node'])

GPU_TEMPERATURE = Gauge('chimera_gpu_temperature_celsius', 
                        'GPU Temperature in Celsius', 
                        ['gpu_id', 'gpu_type', 'node'])

# Histogram to track GPU utilization distribution
GPU_UTIL_HISTOGRAM = Histogram('chimera_gpu_utilization_distribution', 
                              'Distribution of GPU utilization values',
                              ['gpu_id', 'gpu_type', 'node'],
                              buckets=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])

# Counter for monitoring events
MONITORING_CYCLES = Counter('chimera_gpu_monitoring_cycles_total', 
                           'Total number of GPU monitoring cycles')

MONITORING_ERRORS = Counter('chimera_gpu_monitoring_errors_total', 
                           'Total number of GPU monitoring errors',
                           ['error_type'])

def collect_gpu_metrics():
    """Collect metrics from all available GPUs and update Prometheus metrics"""
    try:
        device_count = pynvml.nvmlDeviceGetCount()
        logger.debug(f"Found {device_count} GPU devices")
        
        for i in range(device_count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                
                # Get GPU name/type
                try:
                    name = pynvml.nvmlDeviceGetName(handle)
                except Exception as e:
                    logger.warning(f"Failed to get name for GPU {i}: {e}")
                    name = f"unknown-gpu-{i}"
                
                # Get utilization rates (GPU & memory)
                try:
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    GPU_UTIL.labels(gpu_id=str(i), gpu_type=name, node=NODE_NAME).set(util.gpu)
                    GPU_UTIL_HISTOGRAM.labels(gpu_id=str(i), gpu_type=name, node=NODE_NAME).observe(util.gpu)
                except Exception as e:
                    logger.warning(f"Failed to get utilization for GPU {i}: {e}")
                    MONITORING_ERRORS.labels(error_type="utilization").inc()
                
                # Get memory info
                try:
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    GPU_MEMORY_USED.labels(gpu_id=str(i), gpu_type=name, node=NODE_NAME).set(mem_info.used)
                    GPU_MEMORY_TOTAL.labels(gpu_id=str(i), gpu_type=name, node=NODE_NAME).set(mem_info.total)
                except Exception as e:
                    logger.warning(f"Failed to get memory info for GPU {i}: {e}")
                    MONITORING_ERRORS.labels(error_type="memory").inc()
                
                # Get power usage
                try:
                    power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0  # Convert from mW to W
                    GPU_POWER_USAGE.labels(gpu_id=str(i), gpu_type=name, node=NODE_NAME).set(power)
                except Exception as e:
                    logger.debug(f"Failed to get power usage for GPU {i}: {e}")
                    # Not all GPUs support power measurement, so this is a debug log
                
                # Get temperature
                try:
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                    GPU_TEMPERATURE.labels(gpu_id=str(i), gpu_type=name, node=NODE_NAME).set(temp)
                except Exception as e:
                    logger.warning(f"Failed to get temperature for GPU {i}: {e}")
                    MONITORING_ERRORS.labels(error_type="temperature").inc()
                
            except Exception as e:
                logger.error(f"Error processing GPU {i}: {e}")
                MONITORING_ERRORS.labels(error_type="device_access").inc()
        
        # Increment the monitoring cycle counter
        MONITORING_CYCLES.inc()
        
    except Exception as e:
        logger.error(f"Failed to collect GPU metrics: {e}")
        MONITORING_ERRORS.labels(error_type="collection").inc()

def monitoring_loop():
    """Background thread function to continuously collect GPU metrics"""
    interval = int(os.environ.get("MONITORING_INTERVAL_SECONDS", "15"))
    logger.info(f"Starting GPU monitoring loop with interval {interval} seconds")
    
    while True:
        try:
            collect_gpu_metrics()
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            MONITORING_ERRORS.labels(error_type="loop").inc()
        
        time.sleep(interval)

@app.route('/metrics')
def metrics():
    """Endpoint for Prometheus to scrape metrics"""
    return Response(prometheus_client.generate_latest(), mimetype="text/plain")

@app.route('/health')
def health():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": time.time()}

if __name__ == '__main__':
    # Start the monitoring in a background thread
    monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitoring_thread.start()
    
    # Start the Flask app to expose metrics
    port = int(os.environ.get("PORT", "8000"))
    logger.info(f"Starting metrics server on port {port}")
    app.run(host='0.0.0.0', port=port)
