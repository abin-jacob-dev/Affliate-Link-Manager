#!/bin/bash
# LinkForge Setup Script
set -e

echo "🚀 Setting up LinkForge - Affiliate URL Shortener"
echo ""

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ Virtual environment activated"
else
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "✅ Virtual environment created"
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip install django psycopg2-binary whitenoise gunicorn qrcode[pil] Pillow python-dotenv 2>&1 | tail -3
echo "✅ Dependencies installed"

# Create .env file if not exists
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file..."
    cat > .env << EOF
DJANGO_SECRET_KEY=django-insecure-dev-key-change-in-production-abcdef123456
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
SITE_URL=http://localhost:8000
EOF
    echo "✅ .env file created"
fi

# Create media directory
mkdir -p media/qr_codes
echo "✅ Media directory created"

# Run migrations
echo "🗄️ Running migrations..."
python manage.py makemigrations links analytics
python manage.py migrate
echo "✅ Migrations complete"

# Collect static files
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput 2>&1 || true
echo "✅ Static files collected"

echo ""
echo "🎉 Setup complete!"
echo ""
echo "To start the development server:"
echo "  source venv/bin/activate && python manage.py runserver"
echo ""
echo "Then visit: http://localhost:8000"
