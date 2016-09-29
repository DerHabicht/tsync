#!/bin/python3

from logging import getLogger
from requests import post
from requests import get
from requests import put

logger = getLogger(__name__)


class Trello:
    def __init__(self,
                 key,
                 token,
                 username):
        self.key = key
        self.token = token
        self.username = username
        self.boards = {}

    def _build_api_call(self, api_dest, payload):
        url = "https://api.trello.com/1/" + api_dest

        payload["key"] = self.key
        payload["token"] = self.token

        return url, payload

    def _get(self, api_dest, data):
        url, payload = self._build_api_call(api_dest, data)
        return get(url, payload).json()

    def _put(self, api_dest, data):
        url, payload = self._build_api_call(api_dest, data)
        put(url, payload)

    def _post(self, api_dest, data):
        url, payload = self._build_api_call(api_dest, data)
        post(url, data=payload)

    def get_user_boards(self):
        payload = {"filter": "open"}

        return self._get("members/" + self.username + "/boards", payload)

    def get_board(self, board_name):
        return self.boards.get(board_name.lower(), None)

    def get_board_names(self):
        name_list = []
        for name in self.boards:
            name_list.append(name)

        return name_list

    def load_board(self, id_board, context_name):
        payload = {"fields": "all",
                   "actions": "all",
                   "action_fields": "all",
                   "actions_limit": "1000",
                   "cards": "all",
                   "card_fields": "all",
                   "card_attachments": "true",
                   "labels": "all",
                   "lists": "all",
                   "list_fields": "all",
                   "members": "all",
                   "member_fields": "all",
                   "checklists": "all",
                   "checklist_fields": "all",
                   "organization": "false"}

        self.boards[context_name[0].lower()] = self._get("boards/" + id_board,
                                                         payload)

    def move_card_to_list(self, id_card, id_list):
        payload = {"value": id_list}
        self._put("cards/" + id_card + "/idList", payload)

    def update_check_item(self, id_card, id_check_item, complete):
        payload = {"state": "complete" if complete else "incomplete"}
        self._put("cards/" + id_card + "/checkItem/" + id_check_item, payload)

