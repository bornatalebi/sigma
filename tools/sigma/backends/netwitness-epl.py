# NetWitness EPL output backend for sigmac
# Copyright 2019 Tarik BOUDJEMAA (@snake-jump)
# Inspired from John Tuckner (@tuckner) NetWitness output backend for sigmac

# NetWitness EPL backend for sigmac uses netwitness-epl.yml config file


# RSA Alerts are generated by Event Processing Language (EPL) , that uses Esper Engine (https://www.espertech.com/esper/)
# For more details see :https://community.rsa.com/docs/DOC-110246  and https://community.rsa.com/docs/DOC-80068

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import re
import sigma
from .base import SingleTextQueryBackend
from .mixins import MultiRuleOutputMixin

template="""
module_XXXXX;
@Name('RuleName')
@RSAAlert(oneInSeconds=0) 
SELECT * FROM Event(
    
EXPRESSION
);"""

class NetWitnessEplBackend(SingleTextQueryBackend):
    """Converts Sigma rule into RSA NetWitness EPL . Contributed by @snake-jump"""
    identifier = "netwitness-epl"
    config_required = False
    default_config = ["netwitness-epl"]
    active = True
    reEscape = re.compile('(")')
    ##reEscape = re.compile("([\\|()\[\]{}.^$+])")
    reClear = None
    andToken = " AND "
    orToken = " OR "
    notToken = "NOT"
    subExpression = "(%s)"
    listExpression = "(%s)"
    listSeparator = ", "
    valueExpression = "\'%s\'"
    keyExpression = "%s"
    nullExpression = "%s exists"
    notNullExpression = "%s exists"
    mapExpression = "(%s=%s)"
    mapListsSpecialHandling = True

    def generateMapItemNode(self, node):
        key, value = node
        if type(key) != int:
            key = key.replace(".","_")  ## replace . by _ in meta name (RSA EPL)
            key = key.lower()
        if self.mapListsSpecialHandling == False and type(value) in (str, int, list) or self.mapListsSpecialHandling == True and type(value) in (str, int):
            if type(value) == str and "*" in value[1:-1]:
                value = re.sub('([".^$]|\\\\(?![*?]))', '\\\\\g<1>', value)
                value = re.sub('\\*', '.*', value)
                value = re.sub('\\?', '.', value)
                return "(%s REGEXP %s)" %(key, self.generateValueNode(value))
            elif type(value) == str and "*" in value:
                value = re.sub("(\*\\\\)|(\*)", "", value)
                value = self.generateValueNode("%"+value+"%")  # add "%" to construct the like expression  ex: process like %psexesvc%
                return "(%s LIKE %s)" % (key,value)
            elif type(value) in (str, int):
                return self.mapExpression % (key, self.generateValueNode(value))
            else:
                return self.mapExpression % (key, self.generateNode(value))
        elif type(value) == list:
            return self.generateMapItemListNode(key, value)
        elif value is None:
            return self.nullExpression % (key, )
			
        else:
            raise TypeError("Backend does not support map values of type " + str(type(value)))

    def generateMapItemListNode(self, key, value):
        equallist = list()
        containlist = list()
        regexlist = list()
        for item in value:
            if type(item) == str and "*" in item[1:-1]:
                item = re.sub('([".^$]|\\\\(?![*?]))', '\\\\\g<1>', item)
                item = re.sub('\\*', '.*', item)
                item = re.sub('\\?', '.', item)
                regexlist.append(self.generateValueNode(item))
            elif type(item) == str and (item.endswith("*") or item.startswith("*")):
                item_temp=item
                item = re.sub("(\*\\\\)|(\*)", "", item)
                if item_temp.endswith("*") and item_temp.startswith("*"):   # pattern begins with "*" and ends with "*"
                    containlist.append(self.generateValueNode('%'+item+'%'))  # add "%" to construct the like expression  ex: process like %psexesvc%
                elif item_temp.startswith("*"):   # pattern don't end with "*"
                    containlist.append(self.generateValueNode('%'+item))
                else: # item_temp.endswith("*")  pattern don't begin with "*"
                    containlist.append(self.generateValueNode(item+'%'))
            else:
                equallist.append(self.generateValueNode(item))
        fmtitems = list()
        if equallist:
            if len(equallist) == 1:
                fmtitems.append("%s = %s" % (key, ", ".join(equallist)))
            else:
                # add "(" and ")" to the first and the last item from the list to have  meta_key IN ('value1','value2')	
                equallist[0]=("("+equallist[0])
                equallist[-1]=(equallist[-1]+")")
                fmtitems.append("%s IN %s" % (key, ", ".join(equallist)))
            
        if containlist:
            fmtitems.append("%s LIKE %s" % (key, (" OR "+key+" LIKE ").join(containlist)))
        if regexlist:
            fmtitems.append("%s REGEXP %s" % (key, "|".join(regexlist)))
        fmtquery = "("+" OR ".join(filter(None, fmtitems))
        # Delete the " ' " from the begin or the end of each regex pattern ex : '.*('patern1'|'patern2').*' --> '.*(patern1|patern2).*'
        fmtquery = re.sub('\'\.\*\(\'','\'.*(',fmtquery)
        fmtquery = re.sub('\'\)\.\*\'',').*\'',fmtquery)
        fmtquery = re.sub('\'\|\'','|',fmtquery)
        fmtquery = fmtquery+')'
        return fmtquery

    def generateValueNode(self, node):
        return self.valueExpression % (str(node))

    def generate(self, sigmaparser):
        """Method is called for each sigma rule and receives the parsed rule (SigmaParser)"""
        for parsed in sigmaparser.condparsed:
            query = self.generateQuery(parsed, sigmaparser)
            query=query.replace('INDEX','`index`')  # index is reserved keyword in Esper and must be escaped
            query=template.replace('EXPRESSION', query)
            try:
                query=query.replace('RuleName', sigmaparser.parsedyaml["title"].replace(" ",""))   # add rule name 
                query=query.replace('module_XXXXX', "module "+sigmaparser.parsedyaml["title"].replace(" ","")) # add rule name
            except:
                print("Error when replacing RuleName by Title from yaml")
                pass
            return query

    def generateQuery(self, parsed, sigmaparser):
        result = self.generateNode(parsed.parsedSearch)
        return result
