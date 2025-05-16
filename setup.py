import os
import subprocess
import sys
from pathlib import Path

def create_directories():
    """Create necessary directories if they don't exist."""
    directories = [
        'documents',
        'backend/vectorstore',
        'backend/models',
    ]
    for dir_path in directories:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"Created directory: {dir_path}")

def setup_virtual_environment():
    """Create and setup virtual environment."""
    if not Path('venv').exists():
        subprocess.run([sys.executable, '-m', 'venv', 'venv'])
        print("Created virtual environment")

    # Determine the pip path based on the operating system
    pip_path = 'venv/bin/pip' if os.name != 'nt' else r'venv\Scripts\pip'
    
    # Install requirements
    subprocess.run([pip_path, 'install', '-r', 'backend/requirements.txt'])
    print("Installed Python dependencies")

def setup_frontend():
    """Setup frontend dependencies."""
    if Path('frontend/package.json').exists():
        os.chdir('frontend')
        subprocess.run(['npm', 'install'])
        os.chdir('..')
        print("Installed frontend dependencies")

def main():
    print("Starting project setup...")
    
    # Create directories
    create_directories()
    
    # Setup virtual environment and install dependencies
    setup_virtual_environment()
    
    # Download spaCy model
    subprocess.run([sys.executable, '-m', 'spacy', 'download', 'en_core_web_sm'])
    
    # Setup frontend
    setup_frontend()
    
    print("\nSetup completed successfully!")
    print("\nNext steps:")
    print("1. Place your documents in the 'documents' folder")
    print("2. Update the LLAMA_MODEL_PATH in backend/.env")
    print("3. Run 'python backend/prepare_data.py' to process documents")
    print("4. Start the backend with 'python backend/main.py'")
    print("5. Start the frontend with 'cd frontend && npm start'")

if __name__ == '__main__':
    main() 