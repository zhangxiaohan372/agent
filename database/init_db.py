from database import get_connection

def create_tables():
    connection = get_connection()
    cursor = connection.cursor()
    sql = """
    create table if not exists memories(
         id integer primary key autoincrement,
         content text not null,
         created_at datetime not null default current_timestamp
    )
    """

    cursor.execute(sql)
    connection.commit()
    cursor.close()
    connection.close()

if __name__ == "__main__":
    create_tables()

    print("数据表创建成功")