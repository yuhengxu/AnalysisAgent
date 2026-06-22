@echo off
cd /d %~dp0frontend
echo 请先确保已安装 Node.js 18+
npm install
npm run dev
