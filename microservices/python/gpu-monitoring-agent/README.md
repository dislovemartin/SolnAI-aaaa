# GPU Monitoring Agent

A lightweight monitoring service for NVIDIA GPUs that collects metrics and exposes them for Prometheus scraping.

## Features

- Real-time monitoring of NVIDIA GPU metrics:
  - Utilization (percentage)
  - Memory usage (used and total)
  - Temperature (Celsius)
  - Power usage (Watts)
- Prometheus-compatible metrics endpoint
- Auto-discovery of all available GPUs on the host
- Health check endpoint
- Configurable monitoring interval

## Metrics Exposed

| Metric Name | Description | Labels |
|-------------|-------------|--------|
| `chimera_gpu_utilization_percent` | GPU utilization percentage | `gpu_id`, `gpu_type`, `node` |
| `chimera_gpu_memory_used_bytes` | GPU memory used in bytes | `gpu_id`, `gpu_type`, `node` |
| `chimera_gpu_memory_total_bytes` | Total GPU memory in bytes | `gpu_id`, `gpu_type`, `node` |
| `chimera_gpu_temperature_celsius` | GPU temperature in Celsius | `gpu_id`, `gpu_type`, `node` |
| `chimera_gpu_power_usage_watts` | GPU power usage in watts | `gpu_id`, `gpu_type`, `node` |
| `chimera_gpu_monitoring_cycles_total` | Counter for monitoring cycles | - |
| `chimera_gpu_monitoring_errors_total` | Counter for monitoring errors | `error_type` |

## Requirements

- NVIDIA GPU with compatible drivers
- Python 3.8+
- Dependencies listed in `requirements.txt`

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

The service is configured using environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `MONITORING_INTERVAL_SECONDS` | Interval between metric collections | `15` |
| `PORT` | Port to expose metrics on | `8000` |
| `NODE_NAME` | Node name for metrics | hostname |

## Usage

### Running Locally

```bash
python app.py
```

### Using Docker

```bash
docker build -t gpu-monitoring-agent .
docker run --runtime=nvidia -p 8000:8000 gpu-monitoring-agent
```

### Health Check

Access the health endpoint at: http://localhost:8000/health

### Prometheus Metrics

Access the metrics endpoint at: http://localhost:8000/metrics

## Prometheus Configuration

Add the following to your Prometheus configuration to scrape metrics:

```yaml
scrape_configs:
  - job_name: 'gpu-monitoring'
    scrape_interval: 15s
    static_configs:
      - targets: ['gpu-monitoring-agent:8000']
```

## Kubernetes Deployment

When deploying in Kubernetes, ensure:

1. The pod has access to NVIDIA GPUs
2. Node affinity is set to target nodes with GPUs
3. The NVIDIA runtime is configured

Example node affinity:

```yaml
nodeAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    nodeSelectorTerms:
    - matchExpressions:
      - key: nvidia.com/gpu
        operator: Exists
``` 