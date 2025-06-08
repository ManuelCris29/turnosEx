import os

from config.paths import BASE_DIR


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


DATABASESMYSQL = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',  # Motor para MySQL
        'NAME': 'bdturnosex',    # Nombre de la base de datos que crearás en MySQL
        'USER': 'root',                    # Usuario de MySQL
        'PASSWORD': 'D....odema18****',             # Contraseña de MySQL
        'HOST': 'localhost',                     # Generalmente localhost
        'PORT': '3306',                          # Puerto por defecto de MySQL
    }
}