"""Setup configuration for nats_lib package."""
from setuptools import find_packages, setup

setup(
    name="nats_lib",
    version="0.1.0",
    description="Enhanced NATS client with circuit breaker support",
    author="SolnAI",
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.8",
    install_requires=[
        "nats-py==2.6.0",
        "pybreaker==1.0.1",
        "prometheus-client==0.17.1",
        "loguru==0.7.2",
    ],
    extras_require={
        "test": [
            "pytest==8.0.0",
            "pytest-asyncio==0.23.5",
            "pytest-cov==4.1.0",
            "docker==7.0.0",
        ],
    },
) 