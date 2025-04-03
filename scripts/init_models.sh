#!/bin/bash
set -e

# Make sure NVIDIA API key is available
if [ -z "${NVIDIA_API_KEY}" ]; then
  echo "ERROR: NVIDIA_API_KEY environment variable is not set."
  echo "Please set it before running this script:"
  echo "export NVIDIA_API_KEY=your-nvidia-api-key"
  exit 1
fi

# Create the models directory if it doesn't exist
MODELS_DIR="/app/models"
mkdir -p ${MODELS_DIR}

echo "Initializing models directory for Triton Server..."

# Install NGC CLI if needed for downloading models from NGC registry
NGC_DIR="/app/ngc-cli"
if [ ! -d "$NGC_DIR" ]; then
  echo "Installing NGC CLI..."
  mkdir -p ${NGC_DIR}
  cd /app/llm-router
  unzip -q ngccli_linux.zip -d ${NGC_DIR}
  
  # Add NGC CLI to PATH
  export PATH="${NGC_DIR}/ngc:${PATH}"

  # Configure NGC CLI
  echo "Configuring NGC CLI..."
  ${NGC_DIR}/ngc/ngc config set -k api_key -v ${NVIDIA_API_KEY}
fi

# Download LLM Router models from NGC registry
echo "Downloading LLM Router models..."
cd ${MODELS_DIR}

# Create model directories
mkdir -p task_router_ensemble/1
mkdir -p complexity_router_ensemble/1

echo "Downloading task router model..."
if [ ! -f task_router_ensemble/1/model.pt ]; then
  ${NGC_DIR}/ngc/ngc registry model download-version nvidia/prompt-task-and-complexity-classifier_vtask-llm-router:v0 --dest ${MODELS_DIR}
  cp -r /app/models/prompt-task-and-complexity-classifier_vtask-llm-router/* /app/models/task_router_ensemble/1/
  echo "Task router model downloaded successfully."
else
  echo "Task router model already exists, skipping download."
fi

echo "Downloading complexity router model..."
if [ ! -f complexity_router_ensemble/1/model.pt ]; then
  ${NGC_DIR}/ngc/ngc registry model download-version nvidia/prompt-task-and-complexity-classifier_vcomplexity-llm-router:v0 --dest ${MODELS_DIR}
  cp -r /app/models/prompt-task-and-complexity-classifier_vcomplexity-llm-router/* /app/models/complexity_router_ensemble/1/
  echo "Complexity router model downloaded successfully."
else
  echo "Complexity router model already exists, skipping download."
fi

# Create model configuration files for Triton
echo "Creating model configuration files..."

# Task Router Configuration
cat > ${MODELS_DIR}/task_router_ensemble/config.pbtxt << EOL
name: "task_router_ensemble"
platform: "ensemble"
max_batch_size: 8
input [
  {
    name: "text"
    data_type: TYPE_STRING
    dims: [ 1 ]
  }
]
output [
  {
    name: "prediction"
    data_type: TYPE_STRING
    dims: [ 1 ]
  }
]
ensemble_scheduling {
  step [
    {
      model_name: "task_router"
      model_version: -1
      input_map {
        key: "text"
        value: "text"
      }
      output_map {
        key: "prediction"
        value: "prediction"
      }
    }
  ]
}
EOL

# Complexity Router Configuration
cat > ${MODELS_DIR}/complexity_router_ensemble/config.pbtxt << EOL
name: "complexity_router_ensemble"
platform: "ensemble"
max_batch_size: 8
input [
  {
    name: "text"
    data_type: TYPE_STRING
    dims: [ 1 ]
  }
]
output [
  {
    name: "prediction"
    data_type: TYPE_STRING
    dims: [ 1 ]
  }
]
ensemble_scheduling {
  step [
    {
      model_name: "complexity_router"
      model_version: -1
      input_map {
        key: "text"
        value: "text"
      }
      output_map {
        key: "prediction"
        value: "prediction"
      }
    }
  ]
}
EOL

echo "Model initialization completed successfully."
echo "Triton Server will automatically load the models from ${MODELS_DIR}." 