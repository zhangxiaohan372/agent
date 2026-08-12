try:
    from database.database import DATABASE_PATH, get_connection
except ImportError:
    from database import DATABASE_PATH, get_connection


def create_tables():
    connection = get_connection()
    cursor = connection.cursor()
    sql = """
    create table if not exists memories(
         id integer primary key autoincrement,
         content text not null,
         category text not null,
         importance integer not null default 0,
         embedding text,
         created_at datetime not null default current_timestamp
    )
    """

    cursor.execute(sql)
    connection.commit()
    cursor.close()
    connection.close()


if __name__ == "__main__":
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()

    create_tables()
    print("数据表创建成功")
