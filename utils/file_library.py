# -*- coding: UTF-8 -*-
import os
import hashlib
import logging
import sys
from os import walk
import json
import sqlite3
from contextlib import closing
import os
from pathlib import PurePath
from file.models import File
from file.serializers import FileSerializer

IF_GET_CHECKSUM = False
IF_SAVE_CHECKSUM = True
OS_TYPE = "synology"  # synology, windows
IS_CLEAR_FILE_TABLE = True
DELETE_REPEAT_FILE = False


class FileInit:

    db_file = "db/db.sqlite3"
    log_file = "findIdenticalFiles.log"
    file_total = 0
    file_count = 0

    def logger(self):

        logger = logging.getLogger()
        if not logger.handlers:

            formatter = logging.Formatter(
                '%(asctime)s %(levelname)-8s: %(message)s')

            file_handler = logging.FileHandler(self.log_file)
            file_handler.setFormatter(formatter)

            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.formatter = formatter

            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
            logger.setLevel(logging.INFO)
        return logger

    def is_json(self, myjson):
        try:
            json.loads(myjson)
        except ValueError as e:
            return False
        return True

    def get_md5(self, filename):
        m = hashlib.md5()
        md5_value = None
        mfile = open(filename, "rb")
        if mfile.readable():
            m.update(mfile.read())
            mfile.close()
            md5_value = m.hexdigest()
        return md5_value

    def check_file_modification(self, file_path, file_size, file_mtime, file_ctime, file_md5=None):

        if not os.path.isfile(file_path):
            return False

        if IF_GET_CHECKSUM:
            _md5 = self.get_md5(file_path)

            if (file_md5 == _md5):
                return True
        else:
            _file_size = os.path.getsize(file_path)
            _file_mtime = os.path.getmtime(file_path)
            _file_ctime = os.path.getctime(file_path)

            if (file_size == _file_size and file_mtime == _file_mtime and file_ctime == _file_ctime):
                return False

        return True

    def get_file_info(self, file_path, get_md5=False):
        file_md5 = None
        file_status = None
        isFile = os.path.isfile(file_path)

        if isFile:
            if get_md5:
                file_md5 = self.get_md5(file_path)
            file_size = os.path.getsize(file_path)
            file_mtime = os.path.getmtime(file_path)
            file_ctime = os.path.getctime(file_path)
            file_name, file_extension = os.path.splitext(file_path)

            file_extension = file_extension.lower()

            file_status = {'file_name': file_name, 'file_path': file_path, 'file_md5': file_md5, 'file_size': file_size,
                           'file_mtime': file_mtime, 'file_ctime': file_ctime, 'file_extension': file_extension}

        return file_status

    def get_file_list(self, root_path):

        file_list = []
        for root, _, files in walk(os.path.normpath(root_path)):
            if OS_TYPE == "synology" and '@eaDir' in root:
                continue

            for file in files:
                path = os.path.join(root, file)
                path = os.path.normpath(path)

                file_list.append(path)

        return file_list

    def order_file_table(self, column_name):
        files_db = None
        files_db = File.objects.order_by(column_name)

        return files_db

    def get_file_db(self, file_path):
        db_return = None

        try:
            queryset = File.objects.filter(file_path=file_path)
            serializer = FileSerializer(queryset, many=True)
            db_return = serializer.data
            return db_return

        except Exception:
            pass

        return db_return

    def update_file_status_in_db(self, file_path, file_id):

        file_info = self.get_file_info(file_path, get_md5=IF_SAVE_CHECKSUM)
        if file_info:
            file_size = file_info["file_size"]
            file_mtime = file_info["file_mtime"]
            file_ctime = file_info["file_ctime"]
            file_md5 = file_info["file_md5"]
            try:

                File.objects.filter(id=file_id).update(file_size=file_size, file_mtime=file_mtime,
                                                       file_ctime=file_ctime, file_md5=file_md5)
            except Exception as e:
                print("update file is fault, error:", e)

        return

    def save_file_status(self, file_path):

        file_status = None
        files_db = self.get_file_db(file_path)

        if len(files_db) > 0:
            files_db = files_db[0]
            file_size = files_db["file_size"]
            file_mtime = files_db["file_mtime"]
            file_ctime = files_db["file_ctime"]
            file_id = files_db["id"]
            file_md5 = files_db["file_md5"]

            file_is_modify = self.check_file_modification(file_path,
                                                          file_size,
                                                          file_mtime,
                                                          file_ctime,
                                                          file_md5)

            if (file_is_modify):
                self.update_file_status_in_db(file_path, file_id)

            return

        try:
            file_status = self.get_file_info(
                file_path, get_md5=IF_SAVE_CHECKSUM)
        except Exception as e:
            print("get-file-info is fault, error: ", e)

        serializer = FileSerializer(data=file_status)

        is_valid = serializer.is_valid(raise_exception=True)

        if is_valid:
            db_return = serializer.validated_data

            file_name = db_return["file_name"]
            file_size = db_return["file_size"]
            file_mtime = db_return["file_mtime"]
            file_ctime = db_return["file_ctime"]
            file_md5 = db_return["file_md5"]
            file_extension = db_return["file_extension"]

            try:
                file_object = File(file_name=file_name, file_size=file_size, file_mtime=file_mtime,
                                   file_ctime=file_ctime, file_md5=file_md5, file_path=file_path,
                                   file_extension=file_extension)
                file_object.save()
            except Exception as e:
                print("create file is fault, error:", e)

        return

    def get_same_file_group(self):
        db_return = None
        insertQuery = """
            WITH GroupedData AS (
                SELECT
                    id,
                    file_path,
                    file_md5,
                    file_size,
                    file_mtime,
                    file_ctime,
                    file_extension,
                    created_at,
                    updated_at,
                    DENSE_RANK() OVER (ORDER BY file_md5) AS group_id
                FROM file_file
            )
            SELECT
                group_id,
                id,
                file_path,
                file_md5,
                file_size,
                file_mtime,
                file_ctime,
                file_extension,
                created_at,
                updated_at
            FROM GroupedData
            ORDER BY group_id;
        """

        with closing(sqlite3.connect(self.db_file)) as cnn:
            cursor = cnn.cursor()
            cursor.execute(insertQuery)
            db_return = cursor.fetchall()

        return db_return

    def delete_other_reserve_path_file(self, same_file_record_list, reserve_path):
        for same_file_record in same_file_record_list:
            repeat_file_count = 0
            for file_status in same_file_record:
                file_path = file_status[2]
                file_group_id = file_status[0]
                check_path = PurePath(file_path)

                if (check_path.is_relative_to(reserve_path)):
                    repeat_file_count += 1

                    if DELETE_REPEAT_FILE:
                        if repeat_file_count > 1:
                            print(file_group_id, "delete file(repeat):", file_path)
                            # os.remove(file_path)
                        else:
                            print(file_group_id, "keep file:", file_path)
                    else:
                        print(file_group_id, "keep file:", file_path)
                else:
                    print(file_group_id, "delete file:", file_path)
                    # os.remove(file_path)

    def selete_fils(self, file_list, reserve_path):

        reserve_path = os.path.normpath(reserve_path)
        same_file_record = []
        find_reserve_path = False
        same_file_group_list = []

        for file_status in file_list:
            same_file_record.append(file_status)

            if len(same_file_record) > 1:
                record_group_id_1 = same_file_record[0][0]
                file_group_id = file_status[0]

                if(record_group_id_1 == file_group_id):
                    file_path = file_status[2]
                    check_path = PurePath(file_path)
                    if (check_path.is_relative_to(reserve_path)):
                        find_reserve_path = True
                else:
                    if find_reserve_path:
                        same_file_record.pop()
                        same_file_group_list.append(same_file_record)

                        find_reserve_path = False
                    same_file_record = []
                    same_file_record.append(file_status)

        return same_file_group_list
