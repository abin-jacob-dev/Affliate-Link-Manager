#!/usr/bin/env python3
"""Setup and migration script for the Django project."""
import subprocess
import sys
import os
import shutil

def run_cmd(cmd, cwd=None):
    """Run a shell command and return output."""
    print(f"Running: {cmd}")
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd or os.path.dirname(os.path.abspath(__file__))
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr[:500])
    return result.returncode

def main():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)
    
    # Activate venv
    venv_python = os.path.join(project_dir, 'venv', 'bin', 'python3')
    venv_pip = os.path.join(project_dir, 'venv', 'bin', 'pip')
    
    if not os.path.exists(venv_python):
        print("Virtual environment not found. Creating...")
        run_cmd("python3 -m venv venv")
    
    python = venv_python
    
    # Install dependencies
    print("\n=== Installing dependencies ===")
    run_cmd(f"{venv_pip} install django>=6.0 psycopg2-binary whitenoise gunicorn qrcode[pil] Pillow python-dotenv 2>&1 | tail -5")
    
    # Create .env if needed
    if not os.path.exists('.env'):
        print("\n=== Creating .env file ===")
        with open('.env', 'w') as f:
            f.write("DJANGO_SECRET_KEY=django-insecure-dev-key-change-in-production\n")
            f.write("DJANGO_DEBUG=True\n")
            f.write("DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1\n")
            f.write("SITE_URL=http://localhost:8000\n")
    
    # Create media directory
    os.makedirs('media/qr_codes', exist_ok=True)
    
    # Run migrations
    print("\n=== Running migrations ===")
    run_cmd(f"{python} manage.py makemigrations links analytics")
    run_cmd(f"{python} manage.py migrate")
    
    # Collect static files
    print("\n=== Collecting static files ===")
    run_cmd(f"{python} manage.py collectstatic --noinput --clear 2>&1 | tail -5")
    
    print("\n" + "=" * 50)
    print("✅ Setup complete!")
    print("=" * 50)
    print("\nTo start the server:")
    print("  source venv/bin/activate && python manage.py runserver")
    print("\nThen visit: http://localhost:8000")

if __name__ == '__main__':
    main()
