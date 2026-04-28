import os
import sys

# Remove all db files
for f in os.listdir('.'):
    if f.endswith('.db') or f.endswith('.db-journal'):
        try:
            os.remove(f)
            print(f"✓ Supprimé: {f}")
        except:
            pass

# Now import and init
from app import app, db, init_db, User
with app.app_context():
    db.create_all()
    print("✓ Schéma de base de données créé")
    
    # Add initial users
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password='123', role='admin', nom='Direction GAIA'))
        db.session.commit()
        print("✓ Utilisateur admin créé")
    
    if not User.query.filter_by(username='paul').first():
        db.session.add(User(username='paul', password='123', role='user', nom='Paul Yao'))
        db.session.commit()
        print("✓ Utilisateur paul créé")

print("✓ Base de données initialisée avec succès!")
