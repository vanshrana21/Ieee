#!/bin/bash
# Serve frontend on port 3000

echo "🚀 Serving frontend at http://localhost:3000"
echo "   Press Ctrl+C to stop"
echo ""
echo "   Open in browser: http://localhost:3000/html/login.html"
echo ""

cd /Users/vanshrana/Desktop/IEEE
python -m http.server 3000 --directory .
