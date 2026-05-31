from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient
import eval7
import random
from collections import defaultdict
import os


class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.opponent_stats = defaultdict(lambda: {'FOLD': 0, 'CALL': 0, 'RAISE': 0, 'CHECK': 0})
        self.hand_history = []
        self.hand = []
        self.position = 0
        self.bluff_factor = 0.65  # fucking baseling for retarded ones 
        self.aggression_factor = 1.4  # fucking aggression 
        # weighing according to fuck knows pairs
        self.preflop_equity = {
            'AA': 0.85, 'KK': 0.82, 'QQ': 0.80, 'JJ': 0.78, 'TT': 0.76, '99': 0.74, '88': 0.72, '77': 0.70, '66': 0.68, '55': 0.66, '44': 0.64, '33': 0.62, '22': 0.60,
            'AKs': 0.67, 'AQs': 0.66, 'AJs': 0.65, 'ATs': 0.64, 'A9s': 0.62, 'A8s': 0.61, 'A7s': 0.60, 'A6s': 0.59, 'A5s': 0.58, 'A4s': 0.57, 'A3s': 0.56, 'A2s': 0.55,
            'KQs': 0.64, 'KJs': 0.63, 'KTs': 0.61, 'QJs': 0.62, 'QTs': 0.60, 'JTs': 0.61, 'T9s': 0.59, '98s': 0.58, '87s': 0.57, '76s': 0.56, '65s': 0.55, '54s': 0.54,
            'AKo': 0.65, 'AQo': 0.64, 'AJo': 0.63, 'ATo': 0.62, 'KQo': 0.62, 'KJo': 0.61, 'QJo': 0.60, 'JTo': 0.59, 'T9o': 0.57, '98o': 0.56, '87o': 0.55
        }
        self.premium_hands = ['AA', 'KK', 'QQ', 'AKs', 'AQs']
        self.strong_hands = ['JJ', 'TT', '99', '88', 'AJs', 'KQs', 'AKo', 'AQo']
        self.playable_hands = ['77', '66', '55', '44', '33', '22', 'ATs', 'A9s', 'A8s', 'A7s', 'KJs', 'KTs', 'QJs', 'QTs', 'JTs', 'T9s', '98s', '87s', 'AJo', 'KQo', 'QJo']

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, 
                 big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.hand = [eval7.Card(card) for card in player_hands if card and isinstance(card, str) and len(card) == 2]
        self.all_players = all_players
        self.position = self._calculate_position(all_players)
        self.blind_amount = blind_amount
        self.starting_chips = starting_chips
        self.opponent_stats = defaultdict(lambda: {'FOLD': 0, 'CALL': 0, 'RAISE': 0, 'CHECK': 0})
        self.hand_history = []
        self.bluff_factor = 0.6
        self.aggression_factor = 1.4

    def _calculate_position(self, all_players: List[int]) -> int:
        if len(all_players) < 3:
            return 2 if self.id == all_players[-1] else 0
        idx = all_players.index(self.id)
        return 2 if idx >= len(all_players) * 2 // 3 else (1 if idx >= len(all_players) // 3 else 0)

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        self.current_round = round_state
        self.remaining_chips = max(0, remaining_chips)
        self.round_number = len(self.hand_history) // len(self.all_players) + 1  # Estimate round
        self._update_dynamic_factors()

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        self.current_round = round_state
        self.remaining_chips = max(0, remaining_chips)
        stage = round_state.round.lower()
        pot_size = max(1, round_state.pot)
        to_call = max(0, round_state.current_bet - round_state.player_bets.get(str(self.id), 0))
        min_raise = round_state.min_raise

        # fastly updating according to the opponents shit
        self._update_opponent_stats(round_state.player_actions)

        # Check if retarted bots raised
        opponent_raised = any(action == "RAISE" for pid, action in round_state.player_actions.items() if pid != str(self.id))

        if stage == 'preflop':
            return self._preflop_action(to_call, pot_size, min_raise, opponent_raised)
        return self._postflop_action(to_call, pot_size, min_raise, opponent_raised)

    def _update_opponent_stats(self, player_actions: dict):
        for pid, action in player_actions.items():
            if pid != str(self.id) and action and isinstance(action, str):
                action = action.upper()
                if action in self.opponent_stats[pid]:
                    self.opponent_stats[pid][action] += 1

    def _update_dynamic_factors(self):
        total_actions = sum(sum(stats.values()) for stats in self.opponent_stats.values())
        total_folds = sum(stats.get('FOLD', 0) for stats in self.opponent_stats.values())
        total_raises = sum(stats.get('RAISE', 0) for stats in self.opponent_stats.values())
        fold_freq = total_folds / total_actions if total_actions > 0 else 0.8  # Assume retards will  fold often
        aggression = total_raises / total_actions if total_actions > 0 else 0.05  # retards fucking  rarely raise
        self.bluff_factor = min(0.9, 0.6 + fold_freq * 0.5)  # Bluff apocalypse
        self.aggression_factor = max(1.0, min(2.6, 1.4 + aggression * 0.5))  # lets show them fucking aggression
        # Ramp up in mid-to-late rounds
        if self.round_number >= 2:
            self.aggression_factor = min(3.3, self.aggression_factor + 0.7)
            self.bluff_factor = min(1.0, self.bluff_factor + 0.4)

    def _hand_to_string(self, hand: List[eval7.Card]) -> str:
        if len(hand) != 2:
            return ""
        try:
            ranks = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']
            card1, card2 = hand
            r1 = ranks[12 - card1.rank]
            r2 = ranks[12 - card2.rank]
            if r1 == r2:
                return f"{r1}{r2}"
            suited = 's' if card1.suit == card2.suit else 'o'
            return f"{max(r1, r2)}{min(r1, r2)}{suited}"
        except Exception:
            return ""

    def _preflop_action(self, to_call: int, pot_size: int, min_raise: int, opponent_raised: bool) -> Tuple[PokerAction, int]:
        hand_str = self._hand_to_string(self.hand)
        equity = self.preflop_equity.get(hand_str, 0.3)
        bb = self.blind_amount
        position_factor = [0.3, 1.0, 2.7][self.position]  # Early, middle, late
        is_premium = hand_str in self.premium_hands
        is_strong = hand_str in self.strong_hands
        is_playable = hand_str in self.playable_hands

        # Big raises to dominate default bots
        raise_size = 0
        if is_premium:
            raise_size = int(16 * bb * position_factor * (1 + self.aggression_factor))
        elif is_strong:
            raise_size = int(13 * bb * position_factor * (1 + self.aggression_factor))
        elif is_playable and self.position >= 1:
            raise_size = int(10 * bb * position_factor * (1 + self.aggression_factor))

        # Mid-to-late rounds: all-in with tighter range if stack is low
        if self.round_number >= 2 and self.remaining_chips < 80 * bb and (is_premium or is_strong):
            return PokerAction.ALL_IN, self.remaining_chips

        if to_call == 0:  # First to act
            if raise_size >= min_raise:
                return PokerAction.RAISE, min(raise_size, self.remaining_chips)
            return PokerAction.CHECK, 0
        else:  # Facing a bet
            pot_odds = to_call / (pot_size + to_call) if pot_size > 0 else 0
            if is_premium:
                return PokerAction.RAISE, min(max(raise_size, to_call * 8), self.remaining_chips)
            elif is_strong and to_call <= 0.3 * bb:
                return PokerAction.RAISE, min(max(raise_size, to_call * 8), self.remaining_chips)
            elif is_playable and to_call <= 0.3 * bb and pot_odds < equity + 0.45 and self.position >= 1:
                return PokerAction.CALL, min(to_call, self.remaining_chips)
            elif self.position == 2 and random.random() < self.bluff_factor * 5.5 and to_call <= 0.3 * bb:
                return PokerAction.RAISE, min(max(to_call * 8, raise_size), self.remaining_chips)
            return PokerAction.FOLD, 0

    def _postflop_action(self, to_call: int, pot_size: int, min_raise: int, opponent_raised: bool) -> Tuple[PokerAction, int]:
        community_cards = [eval7.Card(card) for card in self.current_round.community_cards if card and isinstance(card, str) and len(card) == 2]
        hand_strength = self._estimate_hand_strength(community_cards)
        pot_odds = to_call / (pot_size + to_call) if to_call > 0 else 0
        bb = self.blind_amount

        # Crush retards with big raises
        if hand_strength >= 0.75:  # its fucking strong 
            raise_size = int(pot_size * (1.8 + self.aggression_factor * 0.7))
            return PokerAction.RAISE, min(max(raise_size, min_raise), self.remaining_chips)
        elif hand_strength >= 0.5:  # Medium strength
            if to_call == 0:
                raise_size = int(pot_size * (1.5 + self.aggression_factor * 0.6))
                return PokerAction.RAISE, min(max(raise_size, min_raise), self.remaining_chips) if random.random() < 0.95 else (PokerAction.CHECK, 0)
            elif to_call <= 0.3 * bb and pot_odds < hand_strength + 0.45:
                return PokerAction.CALL, min(to_call, self.remaining_chips)
            return PokerAction.FOLD, 0
        else:  # Weak hand
            if to_call == 0 and random.random() < self.bluff_factor * 5.5:
                raise_size = int(pot_size * 1.5)
                return PokerAction.RAISE, min(max(raise_size, min_raise), self.remaining_chips)
            elif to_call <= 0.2 * bb and random.random() < self.bluff_factor * 4.5 and self.position == 2:
                return PokerAction.CALL, min(to_call, self.remaining_chips)
            return PokerAction.CHECK, 0 if to_call == 0 else (PokerAction.FOLD, 0)

    def _estimate_hand_strength(self, community_cards: List[eval7.Card]) -> float:
        if len(self.hand) != 2 or len(community_cards) < 3:
            return 0.3
        try:
            full_hand = self.hand + community_cards
            hand_value = eval7.evaluate(full_hand)
            return min(0.3 + hand_value / 3400, 1.0) 
        except Exception:
            return 0.3

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        self.hand_history.append({
            'round_state': round_state,
            'remaining_chips': remaining_chips
        })

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        self.hand_history.append({
            'final_score': player_score,
            'all_scores': all_scores
        })
