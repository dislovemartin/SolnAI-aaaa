from typing import Dict, List, Any, Optional
import json
import numpy as np
import asyncio
from loguru import logger
import tritonclient.http as httpclient
from tritonclient.utils import InferenceServerException

class TritonClient:
    """Client for interacting with Triton Inference Server."""

    def __init__(self, url: str):
        """Initialize the Triton client.
        
        Args:
            url: URL of the Triton server (e.g., 'localhost:8000')
        """
        self.url = url
        self.client = None
        self.connected = False

    async def connect(self) -> None:
        """Connect to the Triton server."""
        try:
            # Triton HTTP client is synchronous, wrap in executor
            self.client = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: httpclient.InferenceServerClient(url=self.url)
            )
            
            # Check server liveness to verify connection
            is_live = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.is_server_live()
            )
            
            if not is_live:
                logger.error("Triton server is not live")
                self.client = None
                self.connected = False
                return

            # Check available models
            models = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.get_model_repository_index()
            )
            logger.info(f"Connected to Triton server with {len(models)} models available")
            
            self.connected = True
            
        except Exception as e:
            logger.error(f"Failed to connect to Triton server: {e}")
            self.client = None
            self.connected = False
            raise

    async def close(self) -> None:
        """Close the connection to Triton server."""
        self.client = None
        self.connected = False

    async def is_healthy(self) -> bool:
        """Check if the Triton server is healthy."""
        if not self.client:
            return False
            
        try:
            is_live = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.is_server_live()
            )
            is_ready = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.is_server_ready()
            )
            return is_live and is_ready
        except Exception:
            return False

    async def run_summarization(
        self, 
        text: str, 
        max_length: int = 150, 
        min_length: int = 50
    ) -> str:
        """Run text summarization through Triton.
        
        Args:
            text: Text to summarize
            max_length: Maximum length of the summary
            min_length: Minimum length of the summary
            
        Returns:
            Summarized text
        """
        if not self.client or not self.connected:
            raise RuntimeError("Triton client not connected")

        try:
            # Prepare inputs
            text_bytes = text.encode('utf-8')
            inputs = [
                httpclient.InferInput('TEXT_INPUT', [1], "BYTES"),
                httpclient.InferInput('MAX_LENGTH', [1], "INT32"),
                httpclient.InferInput('MIN_LENGTH', [1], "INT32"),
            ]
            inputs[0].set_data_from_numpy(np.array([text_bytes], dtype=np.object_))
            inputs[1].set_data_from_numpy(np.array([max_length], dtype=np.int32))
            inputs[2].set_data_from_numpy(np.array([min_length], dtype=np.int32))

            # Define outputs
            outputs = [
                httpclient.InferRequestedOutput('SUMMARY', binary_data=False),
            ]

            # Make inference request
            request_id = f"summarize-{np.random.randint(0, 10000)}"
            logger.debug(f"Sending summarization request {request_id}")
            
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.infer(
                    model_name='bart_summarization',
                    inputs=inputs,
                    outputs=outputs,
                    request_id=request_id
                )
            )

            # Process results
            summary_bytes = response.as_numpy('SUMMARY')[0]
            summary = summary_bytes.decode('utf-8') if isinstance(summary_bytes, bytes) else str(summary_bytes)
            
            logger.debug(f"Summarization complete: {len(summary)} chars")
            return summary

        except InferenceServerException as e:
            logger.error(f"Triton inference error: {e}")
            raise RuntimeError(f"Summarization inference failed: {e}")
        
        except Exception as e:
            logger.error(f"Summarization error: {e}")
            raise RuntimeError(f"Summarization failed: {e}")

    async def run_entity_extraction(
        self, 
        text: str,
        confidence_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Extract entities from text using Triton.
        
        Args:
            text: Text to extract entities from
            confidence_threshold: Minimum confidence for extracted entities
            
        Returns:
            List of extracted entities
        """
        if not self.client or not self.connected:
            raise RuntimeError("Triton client not connected")

        try:
            # Prepare inputs
            text_bytes = text.encode('utf-8')
            inputs = [
                httpclient.InferInput('TEXT_INPUT', [1], "BYTES"),
                httpclient.InferInput('CONFIDENCE_THRESHOLD', [1], "FP32"),
            ]
            inputs[0].set_data_from_numpy(np.array([text_bytes], dtype=np.object_))
            inputs[1].set_data_from_numpy(np.array([confidence_threshold], dtype=np.float32))

            # Define outputs
            outputs = [
                httpclient.InferRequestedOutput('ENTITIES', binary_data=False),
            ]

            # Make inference request
            request_id = f"extract-entities-{np.random.randint(0, 10000)}"
            logger.debug(f"Sending entity extraction request {request_id}")
            
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.infer(
                    model_name='ner_model',
                    inputs=inputs,
                    outputs=outputs,
                    request_id=request_id
                )
            )

            # Process results
            entities_json = response.as_numpy('ENTITIES')[0]
            entities_str = entities_json.decode('utf-8') if isinstance(entities_json, bytes) else str(entities_json)
            entities = json.loads(entities_str)
            
            logger.debug(f"Entity extraction complete: {len(entities)} entities found")
            return entities

        except InferenceServerException as e:
            logger.error(f"Triton inference error: {e}")
            raise RuntimeError(f"Entity extraction inference failed: {e}")
        
        except Exception as e:
            logger.error(f"Entity extraction error: {e}")
            raise RuntimeError(f"Entity extraction failed: {e}")

    async def run_model(
        self,
        model_name: str,
        inputs_dict: Dict[str, Any],
        output_names: List[str]
    ) -> Dict[str, Any]:
        """Generic method to run any model on Triton.
        
        Args:
            model_name: Name of the model to run
            inputs_dict: Dictionary of input name to numpy array
            output_names: List of output names to request
            
        Returns:
            Dictionary of output name to numpy array
        """
        if not self.client or not self.connected:
            raise RuntimeError("Triton client not connected")

        try:
            # Prepare inputs
            inputs = []
            for name, (data, shape, dtype) in inputs_dict.items():
                inp = httpclient.InferInput(name, shape, dtype)
                inp.set_data_from_numpy(data)
                inputs.append(inp)

            # Define outputs
            outputs = [
                httpclient.InferRequestedOutput(name, binary_data=False)
                for name in output_names
            ]

            # Make inference request
            request_id = f"model-{np.random.randint(0, 10000)}"
            
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.infer(
                    model_name=model_name,
                    inputs=inputs,
                    outputs=outputs,
                    request_id=request_id
                )
            )

            # Process results
            result = {}
            for name in output_names:
                result[name] = response.as_numpy(name)
            
            return result

        except InferenceServerException as e:
            logger.error(f"Triton inference error: {e}")
            raise RuntimeError(f"Model inference failed: {e}")
        
        except Exception as e:
            logger.error(f"Model inference error: {e}")
            raise RuntimeError(f"Model inference failed: {e}")
