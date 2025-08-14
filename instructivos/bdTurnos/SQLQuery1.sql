create database  bd_intercambioturno;

use bd_intercambioturno

drop database bd_intercambioturno;


create table usuario(
id_usuario int identity  primary key,
nombre varchar(45) not null,
apellido1 varchar(45) not null,
apellido2 varchar(45) not null,
correo varchar(100) not null unique,
telefono varchar(15),
tipo_usuario varchar(50) check (tipo_usuario in ('explorador', 'supervisor')) not null,
estado_usuario varchar(20) check (estado_usuario in ('activo', 'inactivo')) default 'activo',
fecha_creacion datetime not null default getdate()
); 

create table loginuser(
id_login int identity primary key,
username varchar(45) not null,
password varchar(255) not null,
fecha_creacion datetime not null default getdate(),
ultimo_inicio datetime null,
fk_id_usuario int foreign key (fk_id_usuario) references usuario (id_usuario)
);

create table turno(
id_turno int identity primary key,
fecha date not null,
Hora_inicio time not null,
hora_final time not null,
nombre_turno varchar(50),
fk_id_usuario int foreign key (fk_id_usuario)  references usuario(id_usuario)
/*
debe existir un atributo DESCANSO  y que sea booleano
*/
);

create table cambio_turno(
id_solicitud int identity primary key, 
estado varchar(50) check(estado in ('pendiente','aprobado','rechazado')),
aprobacion_supervisor bit not null default 0,
aprobacion_recexplorador bit not null default 0,
fecha_solicitud datetime not null default getdate(),
comentarios varchar(255),
fk_turno_solicitante int  foreign key (fk_turno_solicitante) references turno(id_turno),
fk_turno_receptor int  foreign key (fk_turno_receptor) references turno(id_turno)
);

/*
La tabla supervisor_explorador es necesaria para modelar la relación jerárquica entre los supervisores y los exploradores. Permite:

Asignar un supervisor específico a uno o varios exploradores.
Consultar quién es el supervisor de un determinado explorador.
Gestionar las responsabilidades y aprobaciones en el proceso de cambio de turnos, ya que los supervisores tienen un rol importante al aprobar las solicitudes.

Restricción check (id_supervisor != id_explorador): Esta restricción asegura que un supervisor no puede ser asignado como su propio explorador. 
Evita relaciones inválidas donde un usuario sería tanto supervisor como explorador de sí mismo.
*/

create table supervisor_explorador(
    id_supervisor int not null,
    id_explorador int not null,
    primary key (id_supervisor, id_explorador),
    foreign key (id_supervisor) references usuario(id_usuario),
    foreign key (id_explorador) references usuario(id_usuario),
    check (id_supervisor != id_explorador)
);

INSERT INTO usuario (nombre, apellido1, apellido2, correo, telefono, tipo_usuario, estado_usuario, fecha_creacion) VALUES
('Carlos', 'Ramírez', 'Gómez', 'carlos.ramirez@explora.com', '3001234567', 'supervisor', 'activo', GETDATE()),
('Laura', 'Martínez', 'Pérez', 'laura.martinez@explora.com', '3009876543', 'supervisor', 'activo', GETDATE()),
('Ana', 'López', 'Díaz', 'ana.lopez@explora.com', '3012345678', 'explorador', 'activo', GETDATE()),
('Juan', 'García', 'Torres', 'juan.garcia@explora.com', '3018765432', 'explorador', 'activo', GETDATE());

INSERT INTO loginuser (username, password, fecha_creacion, ultimo_inicio, fk_id_usuario) VALUES
('carlos.ramirez', 'password123', GETDATE(), NULL, 1),
('laura.martinez', 'password123', GETDATE(), NULL, 2),
('ana.lopez', 'password123', GETDATE(), NULL, 3),
('juan.garcia', 'password123', GETDATE(), NULL, 4);

INSERT INTO turno (fecha, Hora_inicio, hora_final, nombre_turno, fk_id_usuario) VALUES
('2024-10-21', '08:00', '16:00', 'Turno mañana', 3), -- Turno de Ana López
('2024-10-21', '09:00', '17:00', 'Turno tarde', 4), -- Turno de Juan García
('2024-10-22', '08:00', '16:00', 'Turno mañana', 3), -- Otro turno para Ana López
('2024-10-22', '09:00', '17:00', 'Turno tarde', 4); -- Otro turno para Juan García

INSERT INTO cambio_turno (estado, aprobacion_supervisor, aprobacion_recexplorador, fecha_solicitud, comentarios, fk_turno_solicitante, fk_turno_receptor) VALUES
('pendiente', 0, 0, GETDATE(), 'Cambio solicitado para cubrir un evento', 1, 2), -- Solicitud de cambio entre Ana y Juan (pendiente de aprobación)
('aprobado', 1, 1, GETDATE(), 'Cambio aprobado por ambos exploradores', 3, 4);  -- Solicitud de cambio aprobada entre Ana y Juan para otro día

INSERT INTO supervisor_explorador (id_supervisor, id_explorador) VALUES
(1, 3), -- Carlos supervisa a Ana
(1, 4), -- Carlos supervisa a Juan
(2, 3); -- Laura supervisa también a Ana

select * from cambio_turno











select * from usuario
select * from turno
select * from cambio_turno

select nombre, apellido1, apellido2 from usuario
join cambio_turno on cambio_turno.fk_turno_receptor=usuario.id_usuario

select nombre, apellido1, apellido2, fecha, Hora_inicio, hora_final  from usuario
join turno on turno.fk_id_usuario=usuario.id_usuario
where DATEPART(WEEK, turno.fecha)=DATEPART(YEAR,GETDATE())
and DATEPART(year, turno.fecha) = DATEPART(year, GETDATE());




