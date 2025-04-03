#!/usr/bin/env python3
"""
Mock Triton Inference Server for Integration Testing
Simulates Triton Inference Server responses for testing ML Orchestrator
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import time
from urllib.parse import urlparse, parse_qs
import threading

# Default port for the mock server
PORT = int(os.getenv("PORT", "8000"))

class MockTritonHandler(BaseHTTPRequestHandler):
    """Mock Triton Inference Server HTTP handler."""
    
    def _set_headers(self, status_code=200, content_type="application/json"):
        """Set response headers."""
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Health endpoint
        if path == "/v2/health/ready" or path == "/v2/health/live":
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "ready"}).encode())
            return
            
        # Server metadata
        elif path == "/v2":
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "name": "mock_triton_server",
                "version": "2.30.0",
                "extensions": ["classification", "sequence", "model_repository"]
            }).encode())
            return
            
        # Model metadata
        elif path.startswith("/v2/models"):
            parts = path.split("/")
            if len(parts) >= 4:
                model_name = parts[3]
                
                # Model ready
                if path.endswith("/ready"):
                    self._set_headers(200)
                    self.wfile.write(json.dumps({"ready": True}).encode())
                    return
                    
                # Model metadata
                else:
                    self._set_headers(200)
                    self.wfile.write(json.dumps({
                        "name": model_name,
                        "versions": ["1"],
                        "platform": "pytorch",
                        "inputs": [
                            {"name": "input", "datatype": "FP32", "shape": [-1, 1024]}
                        ],
                        "outputs": [
                            {"name": "output", "datatype": "FP32", "shape": [-1, 1024]}
                        ]
                    }).encode())
                    return
        
        # Default - not found
        self._set_headers(404)
        self.wfile.write(json.dumps({"error": "Not found"}).encode())
    
    def do_POST(self):
        """Handle POST requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        request_body = self.rfile.read(content_length)
        
        try:
            request_json = json.loads(request_body)
        except json.JSONDecodeError:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())
            return
            
        # Model inference
        if path.startswith("/v2/models") and path.endswith("/infer"):
            parts = path.split("/")
            if len(parts) >= 4:
                model_name = parts[3]
                
                # Generate mock response based on model
                response = self._generate_mock_inference(model_name, request_json)
                
                self._set_headers(200)
                self.wfile.write(json.dumps(response).encode())
                return
        
        # Default - not found or not implemented
        self._set_headers(404)
        self.wfile.write(json.dumps({"error": "Not found or not implemented"}).encode())
    
    def _generate_mock_inference(self, model_name, request):
        """Generate mock inference response."""
        # Add a small delay to simulate processing
        time.sleep(0.1)
        
        if model_name == "nlp_enrichment":
            # NLP enrichment model
            return {
                "model_name": model_name,
                "model_version": "1",
                "outputs": [
                    {
                        "name": "output",
                        "datatype": "BYTES",
                        "shape": [1],
                        "data": [{
                            "entities": [
                                {"text": "AI", "label": "TECHNOLOGY", "score": 0.95},
                                {"text": "Neural Networks", "label": "TECHNOLOGY", "score": 0.92}
                            ],
                            "summary": "This is a summary of the input text.",
                            "sentiment": {"positive": 0.8, "negative": 0.1, "neutral": 0.1},
                            "keywords": ["AI", "technology", "research"],
                            "categories": ["Technology", "Science", "Research"]
                        }]
                    }
                ]
            }
        elif model_name == "embedding_model":
            # Vector embedding model
            vector_size = 384
            return {
                "model_name": model_name,
                "model_version": "1",
                "outputs": [
                    {
                        "name": "output",
                        "datatype": "FP32",
                        "shape": [1, vector_size],
                        "data": [0.1] * vector_size  # Mock embedding vector
                    }
                ]
            }
        elif model_name == "classification_model":
            # Classification model
            return {
                "model_name": model_name,
                "model_version": "1",
                "outputs": [
                    {
                        "name": "output",
                        "datatype": "BYTES",
                        "shape": [1],
                        "data": [{
                            "labels": ["technology", "science", "business"],
                            "scores": [0.8, 0.15, 0.05]
                        }]
                    }
                ]
            }
        
        # Default response
        return {
            "model_name": model_name,
            "model_version": "1",
            "outputs": [
                {
                    "name": "output",
                    "datatype": "BYTES",
                    "shape": [1],
                    "data": ["Mock inference result"]
                }
            ]
        }

def run_server(port):
    """Run the HTTP server."""
    server_address = ('', port)
    httpd = HTTPServer(server_address, MockTritonHandler)
    print(f"Starting mock Triton server on port {port}")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server(PORT)
