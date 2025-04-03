#!/usr/bin/env python3
import asyncio
import nats
from nats.js.api import StreamConfig, RetentionPolicy, DiscardPolicy, StorageType
import os
import sys
import argparse
from loguru import logger

async def setup_streams(nats_servers, tls=False):
    # Set up TLS options if enabled
    tls_config = None
    if tls:
        tls_config = {
            "ca_file": os.environ.get("NATS_CA_FILE", "/etc/nats/certs/ca.crt"),
            "cert_file": os.environ.get("NATS_CERT_FILE", "/etc/nats/certs/client.crt"),
            "key_file": os.environ.get("NATS_KEY_FILE", "/etc/nats/certs/client.key")
        }
        logger.info(f"Using TLS with CA: {tls_config['ca_file']}")
    
    # Connect to NATS with TLS if configured
    nc = await nats.connect(
        servers=nats_servers.split(","),
        tls=tls_config
    )
    
    logger.info(f"Connected to NATS server at {nc.connected_url.netloc}")
    
    # Get JetStream context
    js = nc.jetstream()
    
    # Configure streams
    streams = [
        # Real-time inference stream with sharding for latency-critical workloads
        StreamConfig(
            name="REALTIME_INFERENCE",
            subjects=["chimera.inference.realtime.*"],
            retention=RetentionPolicy.LIMITS,
            max_age=86400000000000,  # 24 hours in nanoseconds
            storage=StorageType.FILE,
            num_replicas=3,
            discard=DiscardPolicy.OLD,
            max_bytes=10_000_000_000,  # 10GB
            duplicate_window=120000000000  # 2 minutes
        ),
        
        # Batch inference stream
        StreamConfig(
            name="BATCH_INFERENCE",
            subjects=["chimera.inference.batch.*"],
            retention=RetentionPolicy.LIMITS,
            max_age=604800000000000,  # 7 days in nanoseconds
            storage=StorageType.FILE,
            num_replicas=3,
            discard=DiscardPolicy.OLD,
            max_bytes=50_000_000_000,  # 50GB
        ),
        
        # Audit stream for compliance
        StreamConfig(
            name="AUDIT_LOGS",
            subjects=["chimera.audit.*"],
            retention=RetentionPolicy.LIMITS,
            max_age=7776000000000000,  # 90 days in nanoseconds
            storage=StorageType.FILE,
            num_replicas=3,
            discard=DiscardPolicy.NEW,  # Prevent dropping audit logs
            max_bytes=100_000_000_000,  # 100GB
        )
    ]
    
    # Create or update each stream
    for config in streams:
        try:
            # Try to add the stream
            stream = await js.add_stream(config=config)
            logger.info(f"Created stream {config.name}")
        except nats.js.errors.BadRequestError:
            # Stream exists, update it
            stream = await js.update_stream(config=config)
            logger.info(f"Updated stream {config.name}")
    
    await nc.close()
    logger.info("Stream setup complete")

def main():
    parser = argparse.ArgumentParser(description='Setup NATS JetStream streams for Chimera')
    parser.add_argument('--nats-servers', dest='nats_servers', 
                        default="nats://nats-0.nats:4222,nats://nats-1.nats:4222,nats://nats-2.nats:4222",
                        help='Comma-separated list of NATS server URLs')
    parser.add_argument('--tls', dest='tls', action='store_true',
                        help='Enable TLS for NATS connection')
    
    args = parser.parse_args()
    
    logger.info(f"Setting up streams with servers: {args.nats_servers}")
    asyncio.run(setup_streams(args.nats_servers, args.tls))

if __name__ == "__main__":
    main()
