#!/bin/python3

from logging import getLogger
from logging import Formatter
from logging import StreamHandler
from logging import FileHandler
from logging import DEBUG
from re import search
from taskw.warrior import TaskwarriorError

from settings import trello_conn
from settings import tw_conn
from settings import contexts
from task import Board
from task import Task


def init_trello():
    boards = trello_conn.get_user_boards()

    for board in boards:
        if board["name"].upper() in contexts:
            trello_conn.load_board(board["id"], board["name"].upper())


def build_tr_tasklist(task_dict):
    board_names = trello_conn.get_board_names()

    for name in board_names:
        board = Board(trello_conn.get_board(name))
        task_dict.update(board.get_tasks())


def build_tw_tasklist(task_dict):
    # Set UUIDs and completion state for already parsed tasks
    for _, task in task_dict.items():
        logger.debug("Looking up task %s in Task Warrior.", task.id_check_item)
        if task.id_check_item is None:
            (_, tw_task) = tw_conn.get_task(trelloid=task.id_card + "|")
        else:
            (_, tw_task) = tw_conn.get_task(trelloid=task.id_card + "|"
                                            + task.id_check_item)

        try:
            task.uuid = tw_task["uuid"]
            completion = (True if tw_task["status"] == "completed" else False)
            if completion and not task.complete:
                task.complete = True
                task.update_trello = True
            elif task.complete:
                task.update_taskwarrior = True
        except KeyError:
            if not task.complete:
                task.uuid = None
                task.update_taskwarrior = True

    tw_pending = tw_conn.load_tasks()["pending"]

    for task in tw_pending:
        trelloid = task.get("trelloid", None)

        if trelloid is None:
            description = task["description"]
            context = ""
            for label in task["tags"]:
                if label.upper() in contexts:
                    context = label.lower()
            delay = task["delay"]
            due = task.get("due", "")
            suspense = task.get("suspense", "")
            scheduled = task.get("scheduled", "")
            project = task.get("project", "")
            repo = task.get("repo", "")
            branch = task.get("branch", "")
            uuid = task["uuid"]

            if "dotoday" in task["tags"]:
                dotoday = True
            else:
                dotoday = False

            if "greped" in task["tags"]:
                greped = True
            else:
                greped = False

            task_dict["tw/" + uuid] = Task(description,
                                           context=context,
                                           delay=delay,
                                           due=due,
                                           suspense=suspense,
                                           scheduled=scheduled,
                                           project=project,
                                           repo=repo,
                                           branch=branch,
                                           uuid=uuid,
                                           dotoday=dotoday,
                                           greped=greped)


def read_todotxt(task_dict):
    with open("/home/the-hawk/Dropbox/todo/todo.txt", "r") as todo_file:
        for line in todo_file:
            if line[0] == "x":
                try:
                    task_dict[search(r".*uid:(\S+)")].complete = True
                except KeyError:
                    pass


def build_todotxt(task_dict):
    file_content = ""
    for uid, task in task_dict.items():
        if task.dotoday:
            file_content += task.get_todotxt_string() + " uid:" + uid

    with open("/home/the-hawk/Dropbox/todo/todo.txt", "w") as todo_file:
        print(file_content, todo_file)


def execute_updates(task_dict):
    for _, task in task_dict.items():
        task.update()


def main():
    tasklist = {}

    init_trello()
    build_tr_tasklist(tasklist)
    build_tw_tasklist(tasklist)
    read_todotxt(tasklist)
    execute_updates(tasklist)
    build_todotxt(tasklist)


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

    try:
        main()
    except TaskwarriorError as err:
        logger.fatal("Task Warrior Error:\n"
                     "    Command: " + str(err.command) + "\n"
                     "    stderr: " + str(err.stderr) + "\n"
                     "    stdout: " + str(err.stdout) + "\n")
