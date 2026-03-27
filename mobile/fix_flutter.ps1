# Flutter 修复脚本
Write-Host "Cleaning Flutter build..." -ForegroundColor Yellow
flutter clean

Write-Host "Getting dependencies..." -ForegroundColor Yellow
flutter pub get

Write-Host "Done! Now you can run: flutter run" -ForegroundColor Green
