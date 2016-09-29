#!/bin/python3

from datetime import date
from datetime import datetime
from logging import getLogger
from re import DOTALL
from re import search

from settings import delays
from settings import done_list
from settings import not_sub_lists
from settings import trello_conn


logger = getLogger(__name__)


class Board:
    def __init__(self, board_json):
        def find_list(list_name):
            logger.debug("Searching for list %s.", )
            for trello_list in board_json["lists"]:
                if (trello_list["name"].split()[0].upper() == list_name
                        and not trello_list["closed"]):

                    logger.debug("List %s found on board %s.", list_name,
                                 board_json["name"])
                    return trello_list

            logger.warn("List %s not found on board %s.", list_name,
                        board_json["name"])
            return None

        # Build the list id lookup dictionary
        logger.debug("Building list dictionary for %s.", board_json["name"])
        self.lists = {}
        for delay in delays.items():
            self.lists[delay] = find_list(delay)["id"]
        self.lists[done_list] = find_list(done_list)

        # Build the board labels dictionary
        logger.debug("Building labels dictionary for %s.", board_json["name"])
        self.labels = {}
        for label in board_json["labels"]:
            self.labels[label["id"]] = label["name"].lower()

        # Build the board checklists dictionary
        logger.debug("Building checklists dictionary for %s.",
                     board_json["name"])
        self.checklists = {}
        for checklist in board_json["checklists"]:
            self.checklists[checklist["id"]] = checklist["checkItems"]

        # Parse cards
        logger.debug("Building cards dictionary for %s.", board_json["name"])
        self.cards = []
        for card_json in board_json["cards"]:
            self.cards.append(Card(card_json, board_json["name"], self.labels,
                                   self.board_checklists))

    def get_cards(self):
        return self.cards

    def get_tasks(self):
        task_list = []
        for card in self.cards:
            task_list.append(card.get_tasks())

        return task_list


class Card:
    def __init__(self,
                 card_json,
                 board_name,
                 board_lists,
                 board_labels,
                 board_checklists):

        # Parse the card's description
        desc_attr = Card._parse_description(card_json["desc"])

        try:
            project = board_labels[card_json["idLabels"][0]]
        except IndexError:
            logger.warn("No TLP label set on card %s.", card_json["name"])
            project = ""

        try:
            if project != "":
                project += "."

            # Force an exception if desc_attr["project"] is None
            project = "" + desc_attr["project"]
        except TypeError:
            logger.warn("No project tag set in description for card %s.",
                        card_json["name"])

        # Parse due date
        try:
            match = search(r"(\S+)\..+Z", card_json["due"])
            due = datetime.strptime(match.group(1) + "+0000",
                                    "%Y-%m-%dT%H:%M:%S%z")
        except (AttributeError, TypeError):
            due = None

        # Parse suspense date
        try:
            match = search(r"(\S+)\..+Z", desc_attr["suspense"])
            suspense = datetime.strptime(match.group(1) + "+0000",
                                    "%Y-%m-%dT%H:%M:%S%z")
        except (AttributeError, TypeError):
            suspense = None

        # Parse scheduled date
        try:
            match = search(r"(\S+)\..+Z", desc_attr["scheduled"])
            scheduled = datetime.strptime(match.group(1) + "+0000",
                                          "%Y-%m-%dT%H:%M:%S%z")
        except (AttributeError, TypeError):
            scheduled = None

        if ((due.date() == date.today())
                or (scheduled.date() == date.today())
                or (suspense.date() == date.today())):
            dotoday = True
        else:
            dotoday = False

        # Find the card's delay
        delay = None
        for list_name, list_id in board_lists.items():
            if list_id == card_json["idList"]:
                delay = list_name

        assert delay is not None, "List %s for card %s is not a valid delay." \
                                  % card_json["idList"] % card_json["name"]

        # Create the task list
        self.tasks = {}
        for id_checklist in card_json["idChecklists"]:
            # Add subproject name, if any.
            item_project = project
            if (board_checklists[id_checklist]["name"].upper()
                    not in not_sub_lists):

                if item_project != "":
                    item_project += "."

                item_project += board_checklists[id_checklist]["name"].lower()

            # Add the check items in the checklist
            for check_item in board_checklists[id_checklist]:
                key = "tr/" + card_json["id"] + "|" + check_item["id"]
                self.tasks[key] = Task(check_item["name"],
                                       context=board_name,
                                       delay=delay,
                                       complete=(True if check_item["state"]
                                                 == "complete" else False),
                                       due=due,
                                       suspense=suspense,
                                       scheduled=scheduled,
                                       project=item_project,
                                       repo=desc_attr["repo"],
                                       branch=desc_attr["branch"],
                                       id_card=card_json["id"],
                                       id_check_item=check_item["id"],
                                       dotoday=dotoday,
                                       trello=True)

        # Create the card task
        key = "tr/" + card_json["id"] + "|"
        self.tasks[key] = Task(card_json["name"],
                               context=board_name,
                               delay=delay,
                               complete=(True if delay == done_list else False),
                               due=due,
                               suspense=suspense,
                               scheduled=scheduled,
                               project=project,
                               repo=desc_attr["repo"],
                               branch=desc_attr["branch"],
                               id_card=card_json["id"],
                               dotoday=dotoday,
                               trello=True)

    def get_tasks(self):
        return self.tasks

    @staticmethod
    def _parse_description(desc):
        attributes = ["project", "suspense", "scheduled", "repo", "branch"]
        values = {}

        logger.debug("Checking card for notes.")
        try:
            match = search(r"(.*)\n\n-+", desc, DOTALL)
            values["notes"] = match.group(1)
            logger.debug("Notes found on card.")
        except AttributeError:
            values["notes"] = None
            logger.debug("Notes not found on card.")

        for attribute in attributes:
            logger.debug("Searching description for %s.", attribute)
            try:
                match = search(r".*" + attribute + r":(\S+).*", desc)
                values[attribute] = match.group(1)
                logger.debug("Attribute %s found.", attribute)
            except AttributeError:
                values[attribute] = None
                logger.debug("Attribute %s not found.", attribute)

        return values


class Task:
    def __init__(self,
                 description,
                 context=None,
                 delay=None,
                 complete=False,
                 due=None,
                 suspense=None,
                 scheduled=None,
                 project=None,
                 repo=None,
                 branch=None,
                 uuid=None,
                 id_card=None,
                 id_check_item=None,
                 dotoday=False,
                 greped=False,
                 trello=False
                 ):

        # Set constructor attributes
        self.description = description
        self.context = context
        self.delay = delay
        self.complete = complete
        self.due = due
        self.suspense = suspense
        self.scheduled = scheduled
        self.project = project
        self.repo = repo
        self.branch = branch
        self.uuid = uuid
        self.id_card = id_card
        self.id_check_item = id_check_item
        self.dotoday = dotoday
        self.greped = greped
        self.trello = trello

        # Set update flags
        self.update_trello = False
        self.update_taskwarrior = False

    def update(self):
        if self.update_trello:
            trello_conn.update_check_item(self.id_card, self.id_check_item,
                                          self.complete)

        # TODO: Write Taskwarrior update logic
        if self.update_taskwarrior:
            pass
