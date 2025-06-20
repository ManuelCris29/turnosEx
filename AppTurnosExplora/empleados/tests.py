from django.test import TestCase
from config.wsgi import *
from empleados.models import Role


#listar


#select * from tabla


"""
class RoleTestCase(TestCase):
    def test_list_roles(self):

        rol = Role.objects.create(nombre= 'Explorador')
        rol2 = Role.objects.create(nombre= 'Supervisor')

        roles = Role.objects.all()
        print(roles)

        self.assertEqual(roles.count(), 2)
        self.assertEqual(roles.first().nombre, 'Explorador')
        self.assertEqual(roles.last().nombre, 'Supervisor')
        
 """

#crear
#roles = Role.objects.all()

#r1 = Role()
#r1.nombre = 'Explorador'
#r1.save()

#r2 = Role()
#r2.nombre = 'Supervisor'
#r2.save()

#t = Role(name='manuelksdjk').save()

#editar
#r1= Role.objects.get(id=1)
#r1.nombre = 'Explorador 2'
#r1.save()

#actualizar
#r1= Role.objects.get(id=1)
#r1.nombre = 'Explorador 2'
#r1.save()

#eliminar
#r1= Role.objects.get(id=1)
#r1.delete()

#Filtar datos
#r= Role.objects.filter(nombre__icontains='Expl')
#print(r)
#r= Role.objects.filter(nombre__endswith='Expl')
#print(r)
#r= Role.objects.filter(nombre__in=['Explorador', 'Supervisor'])
#print(r)

#Ordenar datos
#r= Role.objects.order_by('nombre')
#print(r)

#Limitar datos
#r= Role.objects.limit(1)
#print(r)

