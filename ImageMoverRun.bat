@echo off
REM ���z���̃p�X��ݒ�
SET VENV_PATH=venv

REM ���z�������݂��邩�m�F
IF NOT EXIST %VENV_PATH% (
    echo ���z����������܂���B���z�����쐬���܂�...
    python -m venv %VENV_PATH%
)

REM ���z�����A�N�e�B�u��
CALL %VENV_PATH%\Scripts\activate

REM requirements.txt�����݂���ꍇ�̓p�b�P�[�W���C���X�g�[��
IF EXIST requirements.txt (
    echo �p�b�P�[�W���C���X�g�[�����Ă��܂�...
    pip install -r requirements.txt
)

REM ImageMover.py�����s
echo ImageMover.py�����s���Ă��܂�...
python ImageMover.py

REM ���z�����A�N�e�B�u��
deactivate

echo �������������܂����B
pause
