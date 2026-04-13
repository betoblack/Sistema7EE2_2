import pyodbc

def get_db():
    conn = pyodbc.connect(
        'DRIVER={SQL Server};'
        'SERVER=localhost\\SQLEXPRESS;'
        'DATABASE=Integradora;'
        'Trusted_Connection=yes;'
    )
    return conn