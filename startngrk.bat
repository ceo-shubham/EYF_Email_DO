@echo off

:: Start the Streamlit application
echo Starting EaseYourFiling Streamlit app...
start "" cmd /c "streamlit run app.py"

:: Wait a few seconds to allow the app to initialize
timeout /t 5 >nul

:: Launch ngrok to expose the Streamlit port (default 8501)
:: Ensure ngrok is installed and added to your PATH
echo Launching ngrok tunnel on port 8501...
start "" cmd /c "ngrok http 8501"

:: Notify the user
echo.
echo ------------------------------------------------------------
echo The Streamlit app is running at http://localhost:8501
echo ngrok will provide a public URL (check the ngrok console window).
echo Share that public URL with others to let them access the app.
echo ------------------------------------------------------------

pause
