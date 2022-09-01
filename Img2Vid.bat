call %userprofile%\anaconda3\Scripts\activate.bat ldm
:start
set /P id=Enter Images Folder Name And Options : 
python "Img2Vid.py" %id%
goto start
cmd /k