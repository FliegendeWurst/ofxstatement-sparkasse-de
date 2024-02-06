import pdfplumber
import re
from datetime import datetime
from decimal import Decimal as D
import collections

from typing import Iterable

from ofxstatement.plugin import Plugin
from ofxstatement.parser import StatementParser
from ofxstatement.statement import Statement, StatementLine

SEPARATOR = ";;;;----;;;;"

class SparkassePlugin(Plugin):
    """Sparkasse plugin (Germany)"""

    def get_parser(self, filename: str) -> "SparkasseParser":
        return SparkasseParser(filename)


class SparkasseParser(StatementParser[str]):
    def __init__(self, filename: str) -> None:
        super().__init__()
        self.filename = filename
        self.ids = {}

    def parse(self) -> Statement:
        """Main entry point for parsers

        super() implementation will call to split_records and parse_record to
        process the file.
        """
        with pdfplumber.open(self.filename) as pdf:
            self.pdf = pdf
            stmt = super().parse()
            stmt.bank_id = "Sparkasse"
            stmt.account_id = self.account_no
            stmt.currency = "EUR" # assume based on country
            return stmt

    def split_records(self) -> Iterable[str]:
        """Return iterable object consisting of a line per transaction"""
        txns = []
        for page in self.pdf.pages:
            state = None
            date = None
            type = None
            sender = None # or receiver
            desc = None
            amount_num = None
            amount_sign = None
            in_transactions = False
            for line in lines(page):
                # TODO: read initial and final balance
                #print(line, ";")
                regex_account_id = r"(?P<acct_no>\d+), DE\d{2} (\d{4} ){4}\d{2}"
                m = re.search(regex_account_id, line)
                if m is not None:
                    self.account_no = m.group("acct_no")
                    continue
                regex_summary = r"^ ? ?Kontostand am +\d{2}.\d{2}.\d{4} um +\d{2}:\d{2} Uhr"
                if re.search(regex_summary, line) is not None:
                    if date is not None:
                        if amount_sign == "-":
                            amount_num = -amount_num
                        if sender is None:
                                sender = "None"
                        txns.append(date + SEPARATOR + desc + SEPARATOR + sender + SEPARATOR + type + SEPARATOR + str(amount_num))
                        date = None
                    continue
                # transactions look like:
                # 02.03.2020 02.03.2020 Gutschrift e. Überw.
                #                50,00+
                # Sender                       Info/memo
                # 123456ABCD
                # newer format:
                # 01.08.2023 Lastschrift               -32,49
                regex_tx1 = r"^ ?(?P<date>\d{2}\.\d{2}\.\d{4}) \d{2}\.\d{2}\.\d{4} (?P<type>[^+]+) +(?P<amount_num>\d+,\d{2})(?P<amount_sign>[+-])$"
                m = re.search(regex_tx1, line)
                if m is None:
                    regex_tx1c = r"^ ?(?P<date>\d{2}\.\d{2}\.\d{4}) \d{2}\.\d{2}\.\d{4} (?P<type>[^+]+)$"
                    m = re.search(regex_tx1c, line)
                if m is None:
                    regex_tx1b = r"^(?P<date>\d{2}\.\d{2}\.\d{4}) (?P<type>.+) +(?P<amount_sign>[ -])(?P<amount_num>\d+,\d{2})$"
                    m = re.search(regex_tx1b, line)
                if m is not None:
                    #print("NEW TRANSACTION", m, m.groups())
                    # check for previous transaction
                    if date is not None:
                        if amount_sign == "-":
                            amount_num = -amount_num
                        if sender is None:
                            sender = "None"
                        #print(date, desc, sender, type, amount_num)
                        txns.append(date + SEPARATOR + desc + SEPARATOR + sender + SEPARATOR + type + SEPARATOR + str(amount_num))
                        date = None
                    date = m.group("date")
                    type = m.group("type")
                    if "amount_sign" in m.groupdict():
                        amount_num = D(m.group("amount_num").replace(",", "."))
                        amount_sign = m.group("amount_sign")
                        #print(" and", amount_num, amount_sign)
                        desc = None
                        state = "expect_sender"
                    else:
                        state = "expect_amount"
                    continue
                regex_tx2 = r" +(?P<amount_num>\d+,\d{2})(?P<amount_sign>[+-])"
                m = re.search(regex_tx2, line)
                if m is not None:
                    if state != "expect_amount":
                        # check for previous transaction
                        if date is not None:
                            if amount_sign == "-":
                                amount_num = -amount_num
                            if sender is None:
                                sender = "None"
                            txns.append(date + SEPARATOR + desc + SEPARATOR + sender + SEPARATOR + type + SEPARATOR + str(amount_num))
                            date = None
                        continue
                    amount_num = D(m.group("amount_num").replace(",", "."))
                    amount_sign = m.group("amount_sign")
                    state = "expect_sender"
                    continue
                if state == "expect_sender" and not type.startswith("Abrechnung"):
                    # find longest space sequence (two-column layout)
                    found = False
                    for i in range(4, 50):
                        spaces = " " * i
                        if spaces not in line and " " * (i-1) in line:
                            parts = line.split(" " * (i-1))
                            sender = parts[0]
                            desc = parts[1]
                            found = True
                            #print("sd", sender, desc)
                            break
                    if not found:
                        # has to be the one-column layout
                        # (where the sender cannot be determined)
                        sender = None
                        desc = line
                    state = "expect_memo"
                    continue
                if state == "expect_sender" and type.startswith("Abrechnung"):
                    sender = "Sparkasse"
                    desc = line
                    state = "expect_memo"
                    continue
                if state == "expect_memo":
                    # find longest space sequence
                    found = False
                    for i in range(4, 50):
                        spaces = " " * i
                        if spaces not in line and " " * (i-1) in line:
                            parts = line.split(" " * (i-1))
                            if desc is None:
                                desc = parts[0] + " " + parts[1]
                            else:
                                desc = desc + " " + parts[0] + " " + parts[1]
                            found = True
                            break
                    if not found:
                        if desc is None:
                            desc = line
                        else:
                            desc = desc + " " + line
                    continue
            if date is not None:
                if amount_sign == "-":
                    amount_num = -amount_num
                if sender is None:
                    sender = "None"
                txns.append(date + SEPARATOR + desc + SEPARATOR + sender + SEPARATOR + type + SEPARATOR + str(amount_num))
                date = None
        return txns

    def parse_record(self, line: str) -> StatementLine:
        """Parse given transaction line and return StatementLine object"""
        parts = line.split(SEPARATOR)
        date = datetime.strptime(parts[0], "%d.%m.%Y")
        desc = parts[1]
        sender = parts[2]
        type = parts[3]
        m = re.search(r"(?P<type>.+) / Wert: \d{2}.\d{2}.\d{4}", type)
        if m is not None:
            type = m.group("type")
        amount = D(parts[4])
        # ID is simply date + counter
        if parts[0] not in self.ids:
            self.ids[parts[0]] = 0
        id = parts[0] + "-" + str(self.ids[parts[0]] + 1)
        self.ids[parts[0]] = self.ids[parts[0]] + 1
        s = StatementLine(id, date=date, memo=desc, amount=amount)
        if sender != "None":
            s.payee = sender
        s.trntype = "DEBIT"
        if type.startswith("Gutschrift e. Überw.") or type == "Überw. beleglos":
            s.trntype = "XFER"
        elif type.startswith("Abrechnung"):
            s.trntype = "FEE"
        elif type == "Lastschrift":
            s.trntype = "DIRECTDEBIT"
        elif type == "Lohn, Gehalt, Rente":
            # TODO: is there a type for income?
            s.trntype = "XFER"
        elif type == "Kartenzahlung":
            s.trntype = "POS"
        elif type.startswith("Bargeldeinzahlung"):
            s.trntype = "ATM"
        #print(date)
        #print(desc)
        #print(amount)
        return s

def lines(page):
    chars = []
    for obj in page.chars:
        if obj["fontname"] == "Wingdings-Regular" or obj["fontname"] == "ArialMT":
            continue
        if obj["y0"] <= 58:
            continue
        #print(obj["text"], obj["y0"])
        chars.append((-round(obj["y0"]), obj["x0"], obj["text"]))
    chars.sort()
    lines = collections.OrderedDict()
    lastx = 0
    for c in chars:
        y = c[0]
        if y not in lines:
            lines[y] = ""
        if c[1] - lastx > 9.4 or (len(lines[y]) >= 10 and lines[y][-1].isdigit() and c[1] - lastx > 7.6):
            lines[y] = lines[y] + " "
        lines[y] = lines[y] + c[2]
        lastx = c[1]
        #print(y, lines[y])
    return [lines[x] for x in lines]
