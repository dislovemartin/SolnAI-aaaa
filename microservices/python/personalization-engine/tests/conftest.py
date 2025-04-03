import os
import sys

# Add the parent directory to Python path so that app module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) 
