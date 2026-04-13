USE Integradora
GO

CREATE TABLE usuarios (
    id INT PRIMARY KEY IDENTITY(1,1),
    nombre VARCHAR(100),
    correo VARCHAR(100) UNIQUE,
    contraseña VARCHAR(255)
)

ALTER TABLE usuarios
    ADD rol VARCHAR(50)

SELECT * FROM usuarios

INSERT INTO usuarios (nombre, correo, contraseña, rol, tipo_registro, fecha_registro)
VALUES (
    'Jose Rubio',
    'joserubio@gmail.com',
    '123456',
    'admin',
    'manual',
    GETDATE()
);

INSERT INTO usuarios VALUES ('7', 'admin', 'admin@gmail.com', 'admin', 'manual', '2026-02-17 10:03:00.111')

CREATE TABLE materiales (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    descripcion VARCHAR(255),
    cantidad INT NOT NULL CHECK (cantidad >= 0),
    estado VARCHAR(20) NOT NULL
);
GO

CREATE TABLE prestamos (
    id INT IDENTITY(1,1) PRIMARY KEY,
    usuario_id INT NOT NULL,
    material_id INT NOT NULL,
    cantidad INT NOT NULL CHECK (cantidad > 0),
    fecha DATETIME NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'Activo',

    CONSTRAINT fk_prestamo_usuario 
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id),

    CONSTRAINT fk_prestamo_material 
        FOREIGN KEY (material_id) REFERENCES materiales(id)
);
GO

CREATE TABLE devoluciones (
    id INT IDENTITY(1,1) PRIMARY KEY,
    prestamo_id INT NOT NULL,
    fecha DATETIME NOT NULL,
    observaciones VARCHAR(255),

    CONSTRAINT fk_devolucion_prestamo 
        FOREIGN KEY (prestamo_id) REFERENCES prestamos(id)
);
GO

CREATE TABLE pagos_multa (
    id INT IDENTITY(1,1) PRIMARY KEY,
    usuario_id INT NOT NULL,
    prestamo_id INT NULL,
    motivo VARCHAR(20) NOT NULL,
    descripcion VARCHAR(255),
    monto DECIMAL(10,2) NOT NULL,
    moneda VARCHAR(10) NOT NULL DEFAULT 'MXN',
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    paypal_order_id VARCHAR(64),
    paypal_capture_id VARCHAR(64),
    fecha_creacion DATETIME NOT NULL DEFAULT GETDATE(),
    fecha_pago DATETIME NULL,

    CONSTRAINT fk_pago_usuario 
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id),

    CONSTRAINT fk_pago_prestamo 
        FOREIGN KEY (prestamo_id) REFERENCES prestamos(id)
);
GO

INSERT INTO materiales (nombre, descripcion, cantidad, estado)
VALUES 
('Proyector Epson', 'Proyector HD para presentaciones en aula', 3, 'Disponible'),
('Laptop Dell', 'Laptop para exposiciones y clases', 5, 'Disponible'),
('Cable HDMI 2m', 'Cable HDMI de alta velocidad', 10, 'Disponible'),
('Bocina Amplificada', 'Bocina portátil para eventos', 2, 'Disponible'),
('Extensión eléctrica', 'Extensión de 5 metros', 8, 'Disponible');

SELECT * FROM materiales;