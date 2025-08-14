create database  bd_intercambioturno;

use bd_intercambioturno

drop database bd_intercambioturno;

create table usuario(
id_usuario int auto_increment primary key,
nombre varchar(45) not null,
apellido1 varchar(45) not null,
apellido2 varchar(45) not null,
correo varchar(45) not null,
tipo_usuario ENUM('explorador','supervisor') not null
); 

create table turno(
id_turno int auto_increment primary key,
fecha date not null,
Hora_inicio time,
hora_final time,
fk_id_usuario int, 
foreign key (fk_id_usuario)  references usuario(id_usuario)
);

create table cambio_turno(
id_solicitud int auto_increment primary key, 
estado ENUM('pendiente','aprobado','rechazado'),
aprobacion_supervisor bool not null,
aprobacion_recexplorador bool not null,
fk_turno_solicitante int,
fk_turno_receptor int,
foreign key (fk_turno_solicitante) references turno(id_turno),
foreign key (fk_turno_receptor) references turno(id_turno)
);

insert into usuario(nombre, apellido1, apellido2, correo, tipo_usuario  ) value ('Manuel', 'Moreno', 'Lizcano', 'manuel.moreno@parqueexplora.org', 'supervisor'), ('Luis', 'Galvan', 'Coneo', 'luis.galvan@parqueexplora.org', 'explorador')
insert into usuario(nombre, apellido1, apellido2, correo, tipo_usuario  ) value ('marco', 'castillo', 'segundo', 'marco.castillo@parqueexplora.org', 'explorador')
INSERT INTO turno (fecha, Hora_inicio, hora_final, fk_id_usuario) VALUES ('2024-09-04', '08:00:00', '15:00:00', 3);
insert into cambio_turno(estado, aprobacion_supervisor, aprobacion_recexplorador, fk_turno_solicitante, fk_turno_receptor) value ('aprobado',true,true,2,3)
select * from usuario
select * from turno
select * from cambio_turno

