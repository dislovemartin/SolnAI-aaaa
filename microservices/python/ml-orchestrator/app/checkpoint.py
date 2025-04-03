#!/usr/bin/env python3
"""
Checkpoint mechanism for batch inference jobs in Chimera.
Provides resilience for workloads running on spot instances.
"""
import os
import json
import time
import uuid
import argparse
import asyncio
import signal
import boto3
from botocore.exceptions import ClientError
from loguru import logger

# S3 client for persisting checkpoints
s3_client = boto3.client(
    's3',
    region_name=os.environ.get('AWS_REGION', 'eu-west-1'),
    endpoint_url=os.environ.get('S3_ENDPOINT', None)
)
CHECKPOINT_BUCKET = os.environ.get('CHECKPOINT_BUCKET', 'chimera-checkpoints')
LOCAL_CHECKPOINT_DIR = os.environ.get('LOCAL_CHECKPOINT_DIR', '/data/checkpoints')
BATCH_ID = os.environ.get('BATCH_PROCESSOR_ID', str(uuid.uuid4()))

class CheckpointManager:
    """Manages checkpoints for batch inference jobs to provide spot instance resilience."""
    
    def __init__(self, checkpoint_bucket, local_dir, batch_id):
        """Initialize the checkpoint manager.
        
        Args:
            checkpoint_bucket: S3 bucket for checkpoint storage
            local_dir: Local directory for checkpoint staging
            batch_id: Unique ID for this batch processor instance
        """
        self.checkpoint_bucket = checkpoint_bucket
        self.local_dir = local_dir
        self.batch_id = batch_id
        self.current_job = None
        
        # Ensure local directory exists
        os.makedirs(self.local_dir, exist_ok=True)
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT, self._handle_sigterm)
        
        logger.info(f"CheckpointManager initialized with batch ID: {self.batch_id}")
        
    def _handle_sigterm(self, signum, frame):
        """Handle termination signal by triggering final checkpoint."""
        logger.warning(f"Received signal {signum}, initiating final checkpoint")
        if self.current_job:
            asyncio.run(self.save_checkpoint(
                self.current_job, 
                progress=-1,  # -1 indicates interrupted 
                data={'status': 'interrupted', 'timestamp': time.time()}
            ))
        
    async def save_checkpoint(self, job_id, progress, data):
        """Save job progress checkpoint to S3.
        
        Args:
            job_id: Unique ID of the job
            progress: Progress indicator (0-100 or -1 for interrupted)
            data: Dictionary of checkpoint data
            
        Returns:
            True if successful, False otherwise
        """
        self.current_job = job_id
        checkpoint_key = f"batch/{job_id}/checkpoint-{progress}.json"
        local_path = os.path.join(self.local_dir, f"{job_id}-{progress}.json")
        
        # Prepare checkpoint data with metadata
        checkpoint_data = {
            'job_id': job_id,
            'progress': progress,
            'processor_id': self.batch_id,
            'timestamp': time.time(),
            'data': data
        }
        
        # First write locally for speed and durability
        try:
            with open(local_path, 'w') as f:
                json.dump(checkpoint_data, f)
                
            logger.debug(f"Local checkpoint saved: {local_path}")
        except Exception as e:
            logger.error(f"Error saving local checkpoint: {e}")
            return False
        
        # Then upload to S3 for persistence
        try:
            s3_client.put_object(
                Bucket=self.checkpoint_bucket,
                Key=checkpoint_key,
                Body=json.dumps(checkpoint_data),
                ContentType='application/json',
                ServerSideEncryption='AES256'  # Encryption at rest for GDPR/HIPAA
            )
            logger.info(f"Checkpoint saved to S3: {checkpoint_key}")
            return True
        except ClientError as e:
            logger.error(f"Error saving S3 checkpoint: {e}")
            # We still have the local copy, so not a complete failure
            return False
        
    async def load_latest_checkpoint(self, job_id):
        """Load the latest checkpoint for a job.
        
        Args:
            job_id: Unique ID of the job
            
        Returns:
            Checkpoint data dictionary or None if not found
        """
        try:
            # List all checkpoints for this job
            response = s3_client.list_objects_v2(
                Bucket=self.checkpoint_bucket,
                Prefix=f"batch/{job_id}/checkpoint-"
            )
            
            if 'Contents' not in response or not response['Contents']:
                logger.warning(f"No checkpoints found for job {job_id}")
                return None
            
            # Find the checkpoint with the highest progress number
            latest = max(response['Contents'], 
                        key=lambda obj: int(obj['Key'].split('-')[-1].split('.')[0]) 
                        if obj['Key'].split('-')[-1].split('.')[0].isdigit() 
                        else -1)
            
            # Get the checkpoint data
            checkpoint_obj = s3_client.get_object(
                Bucket=self.checkpoint_bucket,
                Key=latest['Key']
            )
            
            checkpoint_data = json.loads(checkpoint_obj['Body'].read().decode('utf-8'))
            logger.info(f"Loaded checkpoint: {latest['Key']}, progress: {checkpoint_data['progress']}")
            
            # Also save locally for future reference
            local_path = os.path.join(self.local_dir, f"{job_id}-{checkpoint_data['progress']}.json")
            with open(local_path, 'w') as f:
                json.dump(checkpoint_data, f)
                
            return checkpoint_data
        
        except ClientError as e:
            logger.error(f"Error loading checkpoint from S3: {e}")
            
            # Try to load from local storage as fallback
            try:
                # Find all local checkpoints for this job
                local_files = [f for f in os.listdir(self.local_dir) 
                            if f.startswith(f"{job_id}-") and f.endswith(".json")]
                
                if not local_files:
                    return None
                
                # Find the latest local checkpoint
                latest_local = max(local_files, 
                                key=lambda f: int(f.split('-')[-1].split('.')[0]) 
                                if f.split('-')[-1].split('.')[0].isdigit() 
                                else -1)
                
                # Load the checkpoint data
                with open(os.path.join(self.local_dir, latest_local), 'r') as f:
                    checkpoint_data = json.loads(f.read())
                
                logger.info(f"Loaded local checkpoint: {latest_local}, progress: {checkpoint_data['progress']}")
                return checkpoint_data
            
            except Exception as local_e:
                logger.error(f"Error loading local checkpoint: {local_e}")
                return None

def main():
    parser = argparse.ArgumentParser(description='Chimera Batch Checkpoint Utility')
    parser.add_argument('--job-id', dest='job_id', help='Job ID to checkpoint')
    parser.add_argument('--progress', dest='progress', type=int, default=0, 
                        help='Progress indicator (0-100)')
    parser.add_argument('--data', dest='data', default='{}',
                        help='JSON string of checkpoint data')
    parser.add_argument('--final', dest='final', action='store_true',
                        help='Perform final checkpoint before termination')
    parser.add_argument('--load', dest='load', action='store_true',
                        help='Load latest checkpoint')
    args = parser.parse_args()
    
    checkpoint_manager = CheckpointManager(
        CHECKPOINT_BUCKET,
        LOCAL_CHECKPOINT_DIR,
        BATCH_ID
    )
    
    if args.final:
        # Get current job from environment or file
        current_job = os.environ.get('CURRENT_JOB_ID')
        if not current_job:
            try:
                with open(os.path.join(LOCAL_CHECKPOINT_DIR, 'current_job'), 'r') as f:
                    current_job = f.read().strip()
            except:
                logger.error("No current job found for final checkpoint")
                return
        
        if current_job:
            logger.warning(f"Performing final checkpoint for job {current_job}")
            asyncio.run(checkpoint_manager.save_checkpoint(
                current_job, 
                -1,  # -1 indicates interrupted
                {'status': 'interrupted', 'timestamp': time.time()}
            ))
    
    elif args.load:
        if not args.job_id:
            logger.error("Job ID required for loading checkpoint")
            return
            
        checkpoint = asyncio.run(checkpoint_manager.load_latest_checkpoint(args.job_id))
        if checkpoint:
            print(json.dumps(checkpoint))
    
    else:
        if not args.job_id:
            logger.error("Job ID required for checkpoint")
            return
            
        # Save the current job ID for potential final checkpoint
        with open(os.path.join(LOCAL_CHECKPOINT_DIR, 'current_job'), 'w') as f:
            f.write(args.job_id)
            
        # Save the checkpoint
        try:
            data = json.loads(args.data)
        except:
            logger.error("Invalid JSON data provided")
            data = {}
            
        asyncio.run(checkpoint_manager.save_checkpoint(args.job_id, args.progress, data))

if __name__ == "__main__":
    main()
