#!/bin/python3

from logging import getLogger
from logging import Formatter
from logging import StreamHandler
from logging import FileHandler
from logging import DEBUG

from settings import trello_conn
from settings import contexts
from task import Board


def init_trello():
    boards = trello_conn.get_user_boards()

    for board in boards:
        if board["name"].upper() in contexts:
            trello_conn.load_board(board["id"], board["name"].upper())


def build_tr_tasklist(task_dict):
    board_names = trello_conn.get_board_names()

    for name in board_names:
        board = Board(trello_conn.get_board(name))
        task_dict.append(board.get_tasks())


def main():
    tasklist = {}

    init_trello()
    build_tr_tasklist(tasklist)


if __name__ == "__main__":
    # Initialize the logger
    logger = getLogger()
    formatter = Formatter(
        fmt="%(asctime)s: [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")

    streamHandler = StreamHandler()
    streamHandler.setFormatter(formatter)
    logger.addHandler(streamHandler)

    fileHandler = FileHandler("logs/tsync.log")
    fileHandler.setFormatter(formatter)
    logger.addHandler(fileHandler)

    logger.setLevel(DEBUG)

    main()
