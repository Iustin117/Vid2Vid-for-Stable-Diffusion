call %userprofile%\anaconda3\Scripts\activate.bat ldm
:start
set /P id=Enter Prompt And Options : 
python "optimizedSD\optimized_vid2vid.py" %id%
goto start
cmd /k