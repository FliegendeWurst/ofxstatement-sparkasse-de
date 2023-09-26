import pdfplumber
import re
from datetime import datetime
from decimal import Decimal as D

from typing import Iterable

from ofxstatement.plugin import Plugin
from ofxstatement.parser import StatementParser
from ofxstatement.statement import Statement, StatementLine

SEPARATOR = ";;;;----;;;;"

class MastercardPlugin(Plugin):
    """Mastercard plugin (Germany)"""

    def get_parser(self, filename: str) -> "MastercardParser":
        return MastercardParser(filename)


class MastercardParser(StatementParser[str]):
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
            if self.bank_id:
                stmt.bank_id = self.bank_id
            stmt.account_id = self.mastercard_no
            stmt.currency = "EUR" # assume based on country
            return stmt

    def split_records(self) -> Iterable[str]:
        """Return iterable object consisting of a line per transaction"""
        txns = []
        for page in self.pdf.pages:
            chars = []
            for obj in page.chars:
                chars.append((-round(obj["y0"]), obj["x0"], obj["text"]))
            chars.sort()
            lines = {}
            lastx = 0
            for c in chars:
                y = c[0]
                if y not in lines:
                    lines[y] = ""
                if c[1] - lastx > 9.4:
                    lines[y] = lines[y] + " "
                lines[y] = lines[y] + c[2]
                lastx = c[1]
            date = None
            desc = None
            amount_num = None
            amount_sign = None
            in_transactions = False
            for line_y in lines:
                line = lines[line_y]
                if line.startswith(" Mastercard-Nummer"):
                    self.mastercard_no = line[len(" Mastercard-Nummer: "):]
                if line.endswith(" Tel.: +49 (0)89 411 116 - 336"):
                    self.bank_id = line[:-len(" Tel.: +49 (0)89 411 116 - 336")]
                if "Saldo letzte Abrechnung" in line or "Übertrag von Seite" in line or "Beleg BuchungVerwendungszweck" in line:
                    in_transactions = True
                    continue
                if line.startswith("Neuer Saldo") or line.startswith("Zwischensumme"):
                    in_transactions = False
                    continue
                if not in_transactions:
                    continue
                # normal statement, spread across multiple lines:
                # 15.08.23 16.08.23 GOOGLE*GOOGLE PLAY APP, 5,99-
                # G.CO/HELPPAY#
                regex = r"(?P<date>\d{2}\.\d{2}\.\d{2}) \d{2}\.\d{2}\.\d{2} (?P<desc>.+) (?P<amount_num>\d+,\d{2})(?P<amount_sign>[-+])"
                regex2 = r"(?P<desc>.+) (?P<amount_num>\d+,\d{2})[-+]"
                m = re.search(regex, line)
                if m is None:
                    # could be split charge: 1,5% für Währungsumrechnung 0,05-
                    m2 = re.search(regex2, line)
                    if m2 is None:
                        desc = desc + " " + line
                    else:
                        desc = desc + " " + m2.group("desc")
                        amount_num_2 = D(m2.group("amount_num").replace(",", "."))
                        # TODO: can the amount_sign differ? (too lazy to implement without evidence)
                        amount_num += amount_num_2
                else:
                    if date is not None:
                        if amount_sign == "-":
                            amount_num = -amount_num
                        txns.append(date + SEPARATOR + desc + SEPARATOR + str(amount_num))
                    date = m.group("date")
                    desc = m.group("desc")
                    amount_num = D(m.group("amount_num").replace(",", "."))
                    amount_sign = m.group("amount_sign")
            if date is not None:
                if amount_sign == "-":
                    amount_num = -amount_num
                txns.append(date + SEPARATOR + desc + SEPARATOR + str(amount_num))
        return txns

    def parse_record(self, line: str) -> StatementLine:
        """Parse given transaction line and return StatementLine object"""
        parts = line.split(SEPARATOR)
        # TODO: this is going to cause trouble in 2100
        # seems like we never learn...
        date = datetime.strptime(parts[0], "%d.%m.%y")
        desc = parts[1]
        amount = D(parts[2])
        # ID is simply date + counter
        if parts[0] not in self.ids:
            self.ids[parts[0]] = 0
        id = parts[0] + "-" + str(self.ids[parts[0]] + 1)
        self.ids[parts[0]] = self.ids[parts[0]] + 1
        s = StatementLine(id, date=date, memo=desc, amount=amount)
        s.trntype = "CREDIT"
        return s
