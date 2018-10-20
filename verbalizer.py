"""
    Contains ways to verbalize sparqls.

    Usage: call verbalizer class over

    SPARQL looks like this:
        {
            "template": "SELECT DISTINCT COUNT(?uri) WHERE {
                    ?x <%(e_out_to_e_out_out)s> <%(e_out_out)s> . ?uri <%(e_to_e_out)s> ?x .
                } ",
            "template_id": 106,
            "n_entities": 1,
            "type": "count",
            "max": 100,
            "query": "SELECT DISTINCT COUNT(?uri) WHERE {
                    ?x <http://dbpedia.org/property/governmentType> <http://dbpedia.org/resource/Suva_City_Council> .
                    ?uri <http://dbpedia.org/property/capital> ?x .
                } ",
            "_id": "cfb7a9fae1074751a52a6115038dc59d",
            "corrected": "false",
            "mapping": {
                    "e_to_e_out": "http://dbpedia.org/property/capital",
                    "class_uri": "http://dbpedia.org/ontology/MusicalArtist",
                    "e_out_to_e_out_out": "http://dbpedia.org/property/governmentType",
                    "e_out_out": "http://dbpedia.org/resource/Suva_City_Council"
                },
            "mapping_type": {
                    "e_to_e_out": "http://www.w3.org/2002/07/owl#Thing",
                    "class_uri": "http://www.w3.org/2002/07/owl#Thing",
                    "e_out_to_e_out_out": "http://www.w3.org/2002/07/owl#Thing",
                    "e_out_out": "http://dbpedia.org/ontology/Organisation"
                },
            "answer_num": {"callret-0": 1}, "answer": {"callret-0": ["2"]}}

        ANOTHER
        {
            "template": " SELECT DISTINCT ?uri WHERE {?uri <%(e_to_e_out)s> <%(e_out)s> . } ",
            "template_id": 1,
            "n_entities": 1,
            "type": "vanilla",
            "max": 100,
            "query": " SELECT DISTINCT ?uri WHERE {
                    ?uri <http://dbpedia.org/property/capital> <http://dbpedia.org/resource/Suva> .
                } ",
            "_id": "01f0be26f67c48028506e999d265d3e2",
            "corrected": "false",
            "mapping": {
                    "e_to_e_out": "http://dbpedia.org/property/capital",
                    "class_uri": "http://dbpedia.org/ontology/MusicalArtist",
                    "e_out": "http://dbpedia.org/resource/Suva"
                },
            "mapping_type": {
                    "e_to_e_out": "http://www.w3.org/2002/07/owl#Thing",
                    "class_uri": "http://www.w3.org/2002/07/owl#Thing",
                    "e_out": "http://dbpedia.org/ontology/City"
                },
            "answer_num": {"uri": 2},
            "answer": {"uri": ["http://dbpedia.org/resource/Fiji", "http://dbpedia.org/resource/Colony_of_Fiji"]}
        }
"""

import uuid
import json
import random
import numpy as np
import numpy.random as npr

from utils.goodies import *
from utils import dbpedia_interface as dbi
from utils import natural_language_utilities as nlutils

NUM_ANSWER_PLURAL = 3


class Templates(object):
    """
        These are what makes the questions. Fill the dict in order you want the decision to be made (plural -> type) etc.
        Add an 's' after variable if you want it to be plural. e.g. e_to_e_out -> e_to_e_out_s

        Ideally, the templates should be automatically picked up by the verbalizing class.
    """
    _1 = FancyDict(vanilla=["%(prefix)s is the <%(class_uri)s> whose <%(e_to_e_out)s> is <%(e_out)s>?",
                            "%(prefix)s <%(e_to_e_out)s> is <%(e_out)s>?"],
                   plural=["%(prefix)s are the things whose <%(e_to_e_out)s> is <%(e_out)s>?",
                           "%(prefix)s <%(e_to_e_out)s> is <%(e_out)s>?"])
    _2 = FancyDict(vanilla=["%(prefix)s is the <%(e_in_to_e)s> of %(e_in)s ?"],
                   plural=["%(prefix)s are the <%(e_in_to_e_s)s> of %(e_in)s?"])
    _101 = FancyDict(vanilla=["How many things are there whose <%(e_to_e_out)s> is <%(e_out)s>?",
                              "Give me a count of things whose <%(e_to_e_out)s> is <%(e_out)s>?"])
    _102 = FancyDict(vanilla=["Count the number of <%(e_in_to_e)s> in <%(e_in)s>?",
                              "Count the <%(e_in_to_e)s> in <%(e_in)s>?",
                              "How many <%(e_in_to_e)s> are there in <%(e_in)s>?"])


class Verbalizer:
    """
        Don't bother creating instances of this thing.
        Use it to get different natural language templates.

        Logic:
            Instantiate with a given template id, it pulls nl templates.
            Then navigates based on the keys mentioned in the templates.
                @TODO: how do make this iterative in nature
            Once decided on a *list* of templates (devoid of rules), it selects randomly b/w them.

            This is done for all diff sparqls, individually.

        @TODO: can we make this filtering perform on the entire group?
        @TODO: figure out all the data we need to make this decision.

    """
    def __init__(self, _id: int):
        self.templates = getattr(Templates, '_'+str(_id))
        self.dbp = dbi.DBPedia(_verbose=False, _caching=True)
        self.flags = [] # List containing sp. conditions for filling this template

    @staticmethod
    def _get_prefix_(datum, _apostrophe=False):
        """
            Returns Who/What or Whose/What's based on apostrophe flag
        :param datum: dict
        :param _apostrophe: bool
        :return: str
        """

        if 'http://dbpedia.org/ontology/Agent' in datum['answer_type'] \
                and "http://dbpedia.org/ontology/Organisation" not in datum['answer_type']:
            return "Who" if not _apostrophe else "Whose"
        else:
            return "What" if not _apostrophe else "What's"

    def _get_template_(self, templates, sparql):
        """
            Recursive fn which finally will home down on a concrete list of templates.

            Logic:
                there will be two keys. One will be named vanilla. One something else.
                E.g. vanilla, plural -> if less than some, choose vanilla. else choose plural
                @TODO: other such constraints

        :param sparql: the data based on which our decisions are made
        :return: list of str/dict based on recursive or not
        """
        if type(templates) is list:
            return templates

        keys = list(templates.keys()).copy()
        keys.pop(keys.index('vanilla'))

        if len(keys) == 0:
            return self._get_template_(templates.vanilla, sparql)



        keys = keys[0]

        if keys == 'plural':
            num_ans = sparql['answer_num']
            self.flags.append('plural')
            return self._get_template_(templates.plural if num_ans >= NUM_ANSWER_PLURAL else templates.vanillla, sparql)

    def _get_sf_(self, map):
        """
            Replace url with its surface form
        :param map: dict
        :return: dict (same keys)
        """
        return {k: self.dbp.get_label(v) if not k == 'prefix' else v for k, v in map.items()}

    def _reset_(self):
        """
            Will reset flags.
        :return: None
        """
        self.flags = []

    def _get_plural_maps_(self, datum):
        """
            Appends plural version of mapping
        :param datum:
        :return:
        """
        datum.update({k+'_s': nlutils.get_plural(v) for k, v in datum.items()})
        return datum

    def verbalize(self, datum):
        """
            Navigate based on particulars of this sparql, and decide what conditions to follow.

        :param datum: dict (mentioned @ start of script)
        :return: dict (mentioned @ start of script) + new fields
        """

        self._reset_()

        # Select the correct template.
        template = npr.choice(self._get_template_(self.templates, datum))

        # Update mapping
        datum['mapping']['prefix'] = self._get_prefix_(datum)
        datum['mapping_sf'] = self._get_sf_(datum['mapping'])

        if 'plural' in self.flags:
            datum['mapping_sf'] = self._get_plural_maps_(datum['mapping_sf'])

        datum['question_verbalized'] = template % datum['mapping_sf']
        datum['question_template'] = template

        return datum


if __name__ == "__main__":
    data_1 = {"template": " SELECT DISTINCT ?uri WHERE {?uri <%(e_to_e_out)s> <%(e_out)s> . } ", "template_id": 1, "n_entities": 1, "type": "vanilla", "max": 100, "query": " SELECT DISTINCT ?uri WHERE {?uri <http://dbpedia.org/property/genre> <http://dbpedia.org/resource/Abstract_strategy_game> . } ", "_id": "75a170adb55245cdb0d63e8fa70cf3bc", "corrected": "false", "entity": "http://dbpedia.org/resource/Chess", "mapping": {"e_to_e_out": "http://dbpedia.org/property/genre", "class_uri": "http://dbpedia.org/ontology/VideoGame", "e_out": "http://dbpedia.org/resource/Abstract_strategy_game"}, "mapping_type": {"e_to_e_out": "http://www.w3.org/2002/07/owl#Thing", "class_uri": "http://www.w3.org/2002/07/owl#Thing", "e_out": "http://dbpedia.org/ontology/MusicGenre"}, "answer_type": ["http://dbpedia.org/ontology/VideoGame", "http://dbpedia.org/ontology/Activity", "http://dbpedia.org/ontology/Game", "http://dbpedia.org/ontology/Sport"], "answer_num": 50, "answer": {"uri": ["http://dbpedia.org/resource/Chess", "http://dbpedia.org/resource/Chinese_checkers", "http://dbpedia.org/resource/Reversi", "http://dbpedia.org/resource/Shogi", "http://dbpedia.org/resource/Abalone_(board_game)", "http://dbpedia.org/resource/Fanorona", "http://dbpedia.org/resource/Hex_(board_game)", "http://dbpedia.org/resource/Nine_Men's_Morris", "http://dbpedia.org/resource/Xiangqi", "http://dbpedia.org/resource/Epaminondas_(game)", "http://dbpedia.org/resource/Renju", "http://dbpedia.org/resource/Arimaa", "http://dbpedia.org/resource/GIPF_(game)", "http://dbpedia.org/resource/YINSH", "http://dbpedia.org/resource/Tori_shogi", "http://dbpedia.org/resource/Terakh", "http://dbpedia.org/resource/Tafl_games", "http://dbpedia.org/resource/Connect_Four", "http://dbpedia.org/resource/DVONN", "http://dbpedia.org/resource/Janggi", "http://dbpedia.org/resource/Dablot_Prejjesne", "http://dbpedia.org/resource/Connect_4x4", "http://dbpedia.org/resource/Chu_shogi", "http://dbpedia.org/resource/Ludus_latrunculorum", "http://dbpedia.org/resource/Circular_chess", "http://dbpedia.org/resource/Terrace_(board_game)", "http://dbpedia.org/resource/Breakthru_(board_game)", "http://dbpedia.org/resource/Alquerque", "http://dbpedia.org/resource/Draughts", "http://dbpedia.org/resource/Go_(game)", "http://dbpedia.org/resource/International_draughts", "http://dbpedia.org/resource/Yot\u00e9", "http://dbpedia.org/resource/Halma", "http://dbpedia.org/resource/Four-player_chess", "http://dbpedia.org/resource/Lasca", "http://dbpedia.org/resource/Russian_draughts", "http://dbpedia.org/resource/Fangqi", "http://dbpedia.org/resource/Spot:_The_Video_Game", "http://dbpedia.org/resource/EuroShogi", "http://dbpedia.org/resource/Four_Fronts", "http://dbpedia.org/resource/Jungle_(board_game)", "http://dbpedia.org/resource/English_draughts", "http://dbpedia.org/resource/Morabaraba", "http://dbpedia.org/resource/Conspirateurs", "http://dbpedia.org/resource/Camelot_(board_game)", "http://dbpedia.org/resource/Cubic_chess", "http://dbpedia.org/resource/Choko_(game)", "http://dbpedia.org/resource/Lines_of_Action", "http://dbpedia.org/resource/Game_of_the_Seven_Kingdoms", "http://dbpedia.org/resource/The_Duke_(board_game)"]}}
    data_2 = {"template": " SELECT DISTINCT ?uri WHERE { <%(e_in)s> <%(e_in_to_e)s> ?uri . } ", "template_id": 2, "n_entities": 1, "type": "vanilla", "max": 100, "query": " SELECT DISTINCT ?uri WHERE { <http://dbpedia.org/resource/Polytechnic_University_of_the_Philippines> <http://dbpedia.org/ontology/sport> ?uri . } ", "_id": "af4eef5b7e4d47a99457fd6c8736b0da", "corrected": "false", "entity": "http://dbpedia.org/resource/Chess", "mapping": {"e_in_to_e": "http://dbpedia.org/ontology/sport", "class_uri": "http://dbpedia.org/ontology/VideoGame", "e_in": "http://dbpedia.org/resource/Polytechnic_University_of_the_Philippines"}, "mapping_type": {"e_in_to_e": "http://www.w3.org/2002/07/owl#Thing", "class_uri": "http://www.w3.org/2002/07/owl#Thing", "e_in": "http://dbpedia.org/ontology/School"}, "answer_type": ["http://dbpedia.org/ontology/Activity", "http://dbpedia.org/ontology/Sport", "http://dbpedia.org/ontology/Game", "http://dbpedia.org/ontology/VideoGame"], "answer_num": 13, "answer": {"uri": ["http://dbpedia.org/resource/Archery", "http://dbpedia.org/resource/Badminton", "http://dbpedia.org/resource/Basketball", "http://dbpedia.org/resource/Chess", "http://dbpedia.org/resource/Tennis", "http://dbpedia.org/resource/Ultimate_(sport)", "http://dbpedia.org/resource/Volleyball", "http://dbpedia.org/resource/Water_polo", "http://dbpedia.org/resource/Football", "http://dbpedia.org/resource/Track_and_field", "http://dbpedia.org/resource/Flying_disc_games", "http://dbpedia.org/resource/Swimming_(sport)", "http://dbpedia.org/resource/Combat_sport"]}}
    data_101 = {"template": " SELECT (COUNT(DISTINCT ?uri) as ?uri) WHERE { ?uri <%(e_to_e_out)s> <%(e_out)s> . } ", "template_id": 101, "n_entities": 1, "type": "count", "max": 100, "query": " SELECT (COUNT(DISTINCT ?uri) as ?uri) WHERE { ?uri <http://dbpedia.org/property/genre> <http://dbpedia.org/resource/Board_game> . } ", "_id": "ef78c4baa0e645149ffb64a00a1f325b", "corrected": "false", "entity": "http://dbpedia.org/resource/Chess", "mapping": {"e_to_e_out": "http://dbpedia.org/property/genre", "class_uri": "http://dbpedia.org/ontology/VideoGame", "e_out": "http://dbpedia.org/resource/Board_game"}, "mapping_type": {"e_to_e_out": "http://www.w3.org/2002/07/owl#Thing", "class_uri": "http://www.w3.org/2002/07/owl#Thing", "e_out": "http://dbpedia.org/ontology/MusicGenre"}, "answer_type": ["http://dbpedia.org/ontology/Activity", "http://dbpedia.org/ontology/Sport", "http://dbpedia.org/ontology/Game", "http://dbpedia.org/ontology/VideoGame"], "answer_num": -1, "answer": {"uri": ["137"]}}
    data_102 = {"template": " SELECT (COUNT(DISTINCT ?uri) as ?uri) WHERE { <%(e_in)s> <%(e_in_to_e)s> ?uri . } ", "template_id": 102, "n_entities": 1, "type": "count", "max": 100, "query": " SELECT (COUNT(DISTINCT ?uri) as ?uri) WHERE { <http://dbpedia.org/resource/Polytechnic_University_of_the_Philippines> <http://dbpedia.org/ontology/sport> ?uri . } ", "_id": "5c16833273134cc684d22d4779094f6f", "corrected": "false", "entity": "http://dbpedia.org/resource/Chess", "mapping": {"e_in_to_e": "http://dbpedia.org/ontology/sport", "class_uri": "http://dbpedia.org/ontology/VideoGame", "e_in": "http://dbpedia.org/resource/Polytechnic_University_of_the_Philippines"}, "mapping_type": {"e_in_to_e": "http://www.w3.org/2002/07/owl#Thing", "class_uri": "http://www.w3.org/2002/07/owl#Thing", "e_in": "http://dbpedia.org/ontology/School"}, "answer_type": ["http://dbpedia.org/ontology/Activity", "http://dbpedia.org/ontology/Sport", "http://dbpedia.org/ontology/Game", "http://dbpedia.org/ontology/VideoGame"], "answer_num": -1, "answer": {"uri": ["13"]}}
    verb = Verbalizer(102)
    data = verb.verbalize(data_102)

    print(data['question_verbalized'])

