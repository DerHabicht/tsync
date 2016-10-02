#!/bin/python3

from datetime import date
from datetime import datetime
from logging import getLogger
from re import DOTALL
from re import search

from settings import delays
from settings import done_list
from settings import not_sub_lists
from settings import priorities
from settings import trello_conn
from settings import tw_conn


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
        for delay, _ in delays.items():
            self.lists[find_list(delay)["id"]] = delay
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
            self.checklists[checklist["id"]] = {}
            self.checklists[checklist["id"]]["name"] = checklist["name"]
            self.checklists[checklist["id"]]["items"] = checklist["checkItems"]

        # Parse cards
        logger.debug("Building cards dictionary for %s.", board_json["name"])
        self.cards = []
        for card_json in board_json["cards"]:
            if not card_json["closed"] and card_json["idList"] in self.lists:
                self.cards.append(Card(card_json, board_json["name"],
                                       self.lists, self.labels,
                                       self.checklists))

    def get_cards(self):
        return self.cards

    def get_tasks(self):
        task_list = {}
        for card in self.cards:
            task_list.update(card.get_tasks())

        return task_list


class Card:
    def __init__(self,
                 card_json,
                 board_name,
                 board_lists,
                 board_labels,
                 board_checklists):

        self.card_json = card_json
        self.board_name = board_name
        self.board_lists = board_lists
        self.board_checklists = board_checklists

        # Parse the card's description
        self.desc_attr = Card._parse_description(card_json["desc"])

        # Get the full project name
        self.project = Card._build_project_string(card_json, board_labels,
                                                  self.desc_attr)

        self.priority = self.desc_attr["priority"]
        if self.priority == "":
            self.priority = "N"

        # Parse the dates
        self.due = Card._parse_date(card_json["due"])
        self.suspense = Card._parse_date(self.desc_attr["suspense"])
        self.scheduled = Card._parse_date(self.desc_attr["scheduled"])

        # Set the dotoday flag
        if (((self.due is not None) and (self.due.date() == date.today()))
            or ((self.scheduled is not None)
                and (self.scheduled.date == date.today()))
            or ((self.suspense is not None)
                and (self.suspense.date == date.today()))):

            self.dotoday = True

        else:
            self.dotoday = False

        # Find the card's delay
        self.delay = board_lists[card_json["idList"]]
        assert self.delay is not None, "List %s for card %s is not a valid " \
                                       "delay." % (card_json["idList"],
                                                   card_json["name"])

        # Create the task list
        self.tasks = self._build_task_list()

        # Create the card task
        key = "tr/" + card_json["id"] + "|"
        self.tasks[key] = Task(card_json["name"],
                               context=board_name,
                               delay=self.delay,
                               complete=(True if self.delay == done_list
                                         else False),
                               priority=self.priority,
                               due=self.due,
                               suspense=self.suspense,
                               scheduled=self.scheduled,
                               project=self.project,
                               repo=self.desc_attr["repo"],
                               branch=self.desc_attr["branch"],
                               id_card=self.card_json["id"],
                               dotoday=self.dotoday,
                               trello=True)

    def get_tasks(self):
        return self.tasks

    @staticmethod
    def _parse_description(desc):
        attributes = ["project", "priority", "suspense", "scheduled", "repo",
                      "branch"]
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

    @staticmethod
    def _build_project_string(card_json, board_labels, desc_attr):
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

        return project

    @staticmethod
    def _parse_date(datestr):
        try:
            # First, try to parse the date string directly
            date_val = datetime.strptime(datestr + "+0000", "%Y%m%dT%H%M%S%z")

        except ValueError:
            try:
                # If this fails, try to regex out the Trello format and parse
                match = search(r"(\S+)\..+Z", datestr)
                date_val = datetime.strptime(match.group(1) + "+0000",
                                        "%Y-%m-%dT%H:%M:%S%z")
            except AttributeError:
                # If this fails, give up
                date_val = None

        except TypeError:
            # This happens if a None is passed in
            date_val = None

        return date_val

    def _build_task_list(self):
        task_list = {}

        for id_checklist in self.card_json["idChecklists"]:
            # Add subproject name, if any.
            item_project = self.project
            if self.board_checklists[id_checklist]["name"].upper() \
                    not in not_sub_lists:

                if item_project != "":
                    item_project += "."

                item_project += self.board_checklists[
                    id_checklist]["name"].lower()

            # Add the check items in the checklist
            for check_item in self.board_checklists[id_checklist]["items"]:
                key = "tr/" + self.card_json["id"] + "|" + check_item["id"]
                task_list[key] = Task(check_item["name"],
                                      context=self.board_name,
                                      delay=self.delay,
                                      complete=(True if check_item["state"]
                                                == "complete" else False),
                                      due=self.due,
                                      suspense=self.suspense,
                                      scheduled=self.scheduled,
                                      project=item_project,
                                      repo=self.desc_attr["repo"],
                                      branch=self.desc_attr["branch"],
                                      id_card=self.card_json["id"],
                                      id_check_item=check_item["id"],
                                      dotoday=self.dotoday,
                                      trello=True)

        return task_list


class Task:
    def __init__(self,
                 description,
                 context=None,
                 delay=None,
                 priority="N",
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
        self.priority = priority
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

        if self.update_taskwarrior:
            # Attempt to retrieve the task from Taskwarrior
            (_, task) = tw_conn.get_task(uuid=self.uuid)

            if task:
                logger.debug("Task %s (%s) found in Taskwarrior.",
                             task["uuid"], task["description"])

                # Update the description
                task["description"] = self.description
                logger.debug("Updated description for task %s to %s.",
                             task["uuid"], task["description"])

            else:
                # Create the task if no UUID
                assert ((self.description is not None)
                        and (self.description != "")), \
                    "Description improperly set on task instantiation."
                task = tw_conn.task_add(self.description)
                self.uuid = task["uuid"]
                logger.info("Created task %s (%s) in Taskwarrior.",
                            task["uuid"], task["description"])

            # Update the context
            assert self.context is not None, \
                "Context improperly set on task instantiation."
            try:
                if self.context.lower() not in task["tags"]:
                    task["tags"].append(self.context.lower())
                    logger.debug("Updated context for task %s (%s) to %s.",
                                 task["uuid"], task["description"],
                                 self.context)

            except KeyError:
                task["tags"] = [self.context.lower()]
                logger.debug("Set context for task %s (%s) to %s.",
                             task["uuid"], task["description"], self.context)

            task["priority"] = self.priority

            # Add special tags as needed
            if self.trello and "trello" not in task["tags"]:
                task["tags"].append("trello")

            if self.greped and "greped" not in task["tags"]:
                task["tags"].append("greped")

            if self.dotoday and "dotoday" not in task["tags"]:
                task["tags"].append("dotoday")

            # Update task delay
            assert self.delay is not None, \
                "Delay improperly set on task instantiation."
            task["delay"] = delays[self.delay.upper()]
            logger.debug("Updated context for task %s (%s) to %s.",
                         task["uuid"], task["description"], task["delay"])

            # Update due date
            if self.due is not None:
                task["due"] = self.due.isoformat()

            # Update suspense date
            if self.suspense is not None:
                task["suspense"] = self.suspense.isoformat()

            # Update scheduled date
            if self.scheduled is not None:
                task["scheduled"] = self.scheduled.isoformat()

            # Update completion state
            assert self.complete is not None, \
                "Completion state improperly set on task instantiation."
            task["status"] = "completed" if self.complete else "pending"

            # Update the project
            task["project"] = self.project

            # Add metadata (if any)
            if self.id_check_item is not None:
                task["trelloid"] = self.id_check_item

            if self.id_card is not None:
                task["trellocardid"] = self.id_card

            # Push the update to Trello
            tw_conn.task_update(task)

    def get_todotxt_string(self):
        return ("(" + priorities[self.priority] + ")" + self.description
                + " +" + self.project + " @" + self.context)
