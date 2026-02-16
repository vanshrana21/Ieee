"""
Migration: Update existing user roles to teacher/student only
Fixes: Convert old roles (faculty, judge, lawyer, admin) to teacher/student
"""
import sqlite3
import os

def migrate():
    # Find the database file
    db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'legalai.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Update faculty, judge, lawyer, admin roles to teacher
    cursor.execute("""
        UPDATE users 
        SET role = 'teacher' 
        WHERE role IN ('faculty', 'judge', 'lawyer', 'admin', 'super_admin', 'FACULTY', 'JUDGE', 'ADMIN')
    """)
    teacher_count = cursor.rowcount
    print(f"✓ Updated {teacher_count} users to 'teacher' role")
    
    # Update any other non-student roles to student
    cursor.execute("""
        UPDATE users 
        SET role = 'student' 
        WHERE role NOT IN ('teacher', 'student')
    """)
    student_count = cursor.rowcount
    print(f"✓ Updated {student_count} users to 'student' role")
    
    # Show current role distribution
    cursor.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
    roles = cursor.fetchall()
    print("\nCurrent role distribution:")
    for role, count in roles:
        print(f"  - {role}: {count} users")
    
    conn.commit()
    conn.close()
    print("\n✅ Role migration complete!")

if __name__ == "__main__":
    migrate()
