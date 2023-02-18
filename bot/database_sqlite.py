import sqlite3
import uuid
from contextlib import closing
from datetime import datetime
from typing import Any, Optional


class SqliteDataBase:

    def __init__(self, sqlite_uri: str):
        self.db_conn = sqlite3.connect(sqlite_uri)
        with closing(self.db_conn.cursor()) as cursor:
            cursor.execute("CREATE TABLE IF NOT EXISTS users("
                           "_id INT PRIMARY KEY NOT NULL, "
                           "chat_id INT NOT NULL, "
                           "username TEXT, "
                           "first_name TEXT, "
                           "last_name TEXT, "
                           "last_interaction INT NOT NULL, "
                           "first_seen INT NOT NULL, "
                           "current_dialog_id TEXT, "
                           "current_chat_mode TEXT NOT NULL, "
                           "n_used_tokens INT NOT NULL)")
            cursor.execute("CREATE TABLE IF NOT EXISTS dialogs("
                           "_id TEXT PRIMARY KEY NOT NULL, "
                           "user_id INT NOT NULL, "
                           "chat_mode INT NOT NULL, "
                           "start_time INT NOT NULL)")
            cursor.execute("CREATE TABLE IF NOT EXISTS messages("
                           "_date INT PRIMARY KEY NOT NULL, "
                           "user_id INT NOT NULL, "
                           "dialog_id TEXT NOT NULL, "
                           "user TEXT, "
                           "bot TEXT)")
            self.db_conn.commit()

    def close(self):
        self.db_conn or self.db_conn.close()

    def check_if_user_exists(self, user_id: int, raise_exception: bool = False):
        if self.__get_table_attribute("users", ("_id", user_id), "_id") is not None:
            return True
        else:
            if raise_exception:
                raise ValueError(f"User {user_id} does not exist")
            else:
                return False

    def add_new_user(
            self,
            user_id: int,
            chat_id: int,
            username: str = "",
            first_name: str = "",
            last_name: str = "",
    ):
        if not self.check_if_user_exists(user_id):
            time_now = datetime.now().timestamp()
            self.__insert_table_row("users", [
                user_id,  # _id
                chat_id,  # chat_id
                username,  # username
                first_name,  # first_name
                last_name,  # last_name
                time_now,  # last_interaction
                time_now,  # first_seen
                None,  # current_dialog_id
                "assistant",  # current_chat_mode
                0  # n_used_tokens
            ])

    def start_new_dialog(self, user_id: int):
        self.check_if_user_exists(user_id, raise_exception=True)

        dialog_id = str(uuid.uuid4())

        # add new dialog
        self.__insert_table_row("dialogs", [
            dialog_id,  # _id
            user_id,  # user_id
            self.get_user_attribute(user_id, "current_chat_mode"),  # chat_mode
            datetime.now().timestamp(),  # start_time
        ])

        # update user's current dialog
        self.__update_table_row("users", ("_id", user_id), {
            "current_dialog_id": dialog_id
        })

        return dialog_id

    def get_user_attribute(self, user_id: int, key: str):
        self.check_if_user_exists(user_id, raise_exception=True)
        with closing(self.db_conn.cursor()) as cursor:
            res = cursor.execute(f"SELECT {key} FROM users WHERE _id='{user_id}' LIMIT 1").fetchone()
            if res is None or len(res) == 0:
                raise ValueError(f"User {user_id} does not have a value for {key}")
            return res[0]

    def set_user_attribute(self, user_id: int, key: str, value: Any):
        self.check_if_user_exists(user_id, raise_exception=True)
        self.__update_table_row("users", ("_id", user_id), {key: value})

    def get_dialog_messages(self, user_id: int, dialog_id: Optional[str] = None):
        self.check_if_user_exists(user_id, raise_exception=True)
        dialog_id = dialog_id or self.get_user_attribute(user_id, "current_dialog_id")
        with closing(self.db_conn.cursor()) as cursor:
            res = cursor.execute(f"SELECT user,bot,_date FROM messages "
                                 f"WHERE dialog_id={dialog_id} AND user_id={user_id} "
                                 f"ORDER BY _date")
            return map(
                lambda item: {"user": item[0], "bot": item[1], "date": datetime.fromtimestamp(int(item[2]))},
                res
            )

    def append_dialog_message(self, user_id: int, new_dialog_message: dict, dialog_id: Optional[str] = None):
        self.check_if_user_exists(user_id, raise_exception=True)
        dialog_id = dialog_id or self.get_user_attribute(user_id, "current_dialog_id")
        self.__insert_table_row("messages", [
            new_dialog_message["date"].timestamp(),  # _date
            user_id,
            dialog_id,
            new_dialog_message["user"],  # user
            new_dialog_message["bot"],  # bot
        ])

    def remove_dialog_last_message(self, user_id: int, dialog_id: Optional[str] = None):
        dialog_id = dialog_id or self.get_user_attribute(user_id, "current_dialog_id")
        with closing(self.db_conn.cursor()) as cursor:
            cursor.execute(f"DELETE FROM messages "
                           f"WHERE _date=(SELECT MAX(_date) FROM messages WHERE dialog_id={str(dialog_id)} LIMIT 1) "
                           f"AND dialog_id={str(dialog_id)}")
            self.db_conn.commit()

    def __insert_table_row(self, table_name: str, datas: list):
        sql_str = f"INSERT INTO {table_name} VALUES("
        should_add_comma = False
        for d in datas:
            if should_add_comma:
                sql_str += ","
            if isinstance(d, str):
                sql_str += f"'{d}'"
            elif d is None:
                sql_str += "null"
            else:
                sql_str += str(d)
            should_add_comma = True
        sql_str += ")"
        with closing(self.db_conn.cursor()) as cursor:
            cursor.execute(sql_str)
            self.db_conn.commit()

    def __update_table_row(self, table_name: str, where: tuple, datas: dict):
        sql_str = f"UPDATE {table_name} SET "
        for k, v in datas.items():
            if isinstance(v, datetime):
                v = v.timestamp()
            elif isinstance(v, str):
                v = f"'{v}'"
            else:
                v = str(v)
            sql_str += f"{str(k)}={v}, "
        sql_str = f"{sql_str[0:-2]} WHERE {str(where[0])} = {str(where[1])}"
        with closing(self.db_conn.cursor()) as cursor:
            cursor.execute(sql_str)
            self.db_conn.commit()

    def __get_table_attribute(self, table_name: str, where: tuple, key: str):
        with closing(self.db_conn.cursor()) as cursor:
            res = cursor \
                .execute(f"SELECT {key} FROM {table_name} WHERE {str(where[0])}={str(where[1])} LIMIT 1") \
                .fetchone()
            return res[0] if res is not None and len(res) > 0 else None
