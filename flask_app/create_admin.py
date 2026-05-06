from app import app, db
from database import User

with app.app_context():
    # Réinitialisation de la base si besoin
    db.drop_all()
    db.create_all()
    # Création de l'administrateur
    admin = User(username="admin")
    admin.set_email("root@gmail.com")
    admin.set_password("root")
    admin.set_region("NorthAmerica")
    admin.is_admin = True
    admin.set_alerts_enabled(True)

    db.session.add(admin)
    db.session.commit()

    print("Base de données réinitialisée et administrateur créé avec succès !")
    print("Identifiants : root@gmail.com / root")
