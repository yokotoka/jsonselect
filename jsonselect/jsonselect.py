"""
*                   Any node                                                                                    1
T                   A node of type T, where T is one string, number, object, array, boolean, or null            1
T.key               A node of type T which is the child of an object and is the value its parents key property  1
T."complex key"     Same as previous, but with property name specified as a JSON string                         1
T:root              A node of type T which is the root of the JSON document                                     1
T:nth-child(n)      A node of type T which is the nth child of an array parent                                  1
T:nth-last-child(n) A node of type T which is the nth child of an array parent counting from the end            2
T:first-child       A node of type T which is the first child of an array parent                                1
T:last-child        A node of type T which is the last child of an array parent                                 2
T:only-child        A node of type T which is the only child of an array parent                                 2
T:empty             A node of type T which is an array or object with no child                                  2
T U                 A node of type U with an ancestor of type T                                                 1
T > U               A node of type U with a parent of type T                                                    1
T ~ U               A node of type U with a sibling of type T                                                   2
S1, S2              Any node which matches either selector S1 or S2                                             1
T:has(S)            A node of type T which has a child node satisfying the selector S                           3
T:expr(E)           A node of type T with a value that satisfies the expression E                               3
T:val(V)            A node of type T with a value that is equal to V                                            3
T:contains(S)       A node of type T with a string value contains the substring S                               3


IDEA:

    each production returns a list of matching nodes. Do set arithmetic at higher levels?
    This might work because we'll be working with Nodes and not primitives

    i.e.
    expr_prod:
        and(results, type_prod)
        and(results, id_prod)
        and(results, pclass_prod)
        if next == ','
            or(results, expr_prod)
        if next == ' '
            ancestor(results, expr_prod)
        if next == '~':
            sibling(results, expr_prod)
        if next == '>'
            parent(results, expr_prod)
        return results

    might be hard to do set arithmetic because node.value could be an unhashable primitive.
    perhaps going back to adding validators.
    or a hybrid approach where and/or adds validators
"""
import re
import numbers
import collections
import functools


S_TYPE = lambda x, token: ('type', token)
S_IDENTIFIER = lambda x, token: ('identifier', token[1:])
S_QUOTED_IDENTIFIER = lambda x, token: S_IDENTIFIER(None, token.replace('"', ''))
S_PCLASS = lambda x, token: ('pclass', token[1:])
S_PCLASS_FUNC = lambda x, token: ('pclass_func', token[1:])
S_OPER = lambda x, token: ('operator', token)
S_EMPTY = lambda x, token:  ('empty', True)
S_UNK = lambda x, token: ('unknown', token)
S_INT = lambda x, token: ('int', int(token))
S_FLOAT = lambda x, token: ('float', float(token))
S_WORD = lambda x, token: ('word', token)
S_BINOP = lambda x, token: ('binop', token)
S_VALS = lambda x, token: ('val', token)

SCANNER = re.Scanner([
    (r"[~*,>\)\(]", S_OPER),
    (r"\s", S_EMPTY),
    (r"(-?\d+(\.\d*)([eE][+\-]?\d+)?)", S_FLOAT),
    (r"\d+", S_INT),
    (r"string|boolean|null|array|object|number", S_TYPE),
    (r'\.?\"([^"\\]|\\[^"])*\"', S_QUOTED_IDENTIFIER),
    (u"\.([_a-zA-Z]|[^\0-\0177]|\\[^\s0-9a-fA-F])(?:[_a-zA-Z0-9\-]" \
     u"|[^\u0000-\u0177]|(?:\\[^\s0-9a-fA-F]))*", S_IDENTIFIER),
    (r":(root|first-child|last-child|only-child)", S_PCLASS),
    (r":(nth-child|nth-last-child|has|expr|val|contains)", S_PCLASS_FUNC),
    (r"(&&|\|\||[\$\^<>!\*]=|[=+\-*/%<>])", S_BINOP),
    (r"true|false|null", S_VALS),
    (r"\w+", S_WORD),
])


def lex(selector):
    tokens, rest = SCANNER.scan(selector)
    if not len(tokens):
        if rest:
            raise Exception("leftover input: %s" % rest)
    return tokens

# parents is a list of node names along the path from the root to current node
# sibling_idx is 1 indexed
Node = collections.namedtuple('Node', ['value', 'parents', 'sibling_idx',
                                       'siblings'])

def object_iter(obj, parents=[], sibling_idx=None, siblings=None):
    """
    Yields each node of object graph in postorder
    """

    if isinstance(obj, list):
        _siblings = len(obj)
        for i, elem in enumerate(obj):
            for node in object_iter(elem, parents, i+1, _siblings):
                yield node
    elif isinstance(obj, collections.Mapping):
        for key in obj:
            for node in object_iter(obj[key], parents + [key]):
                yield node
    yield Node(value=obj, parents=parents, siblings=siblings,
               sibling_idx=sibling_idx)



class Parser(object):

    def __init__(self, obj):
        self.obj = obj

    def _eval(self, validators, obj):
        results = []
        for node in object_iter(obj):
            if all([validate(node) for validate in validators]):
                results.append(node)
        return results

    def parse(self, tokens):

        if self._peek(tokens, 'operator') == '*':
            self._match(tokens, 'operator')
            return [node.value for node in object_iter(self.obj)]
        else:
            results = self.selector_production(tokens)
            results = [node.value for node in results]
            # single results should be returned as a primitive
            if len(results) == 1:
                return results[0]
            return results
    
    def selector_production(self, tokens):

        validators = []
        # productions should add their own nodes to the found list
        if self._peek(tokens, 'type'):
            type_ = self._match(tokens, 'type')
            validators.append(self.type_production(type_))

        if self._peek(tokens, 'identifier'):
            key = self._match(tokens, 'identifier')
            validators.append(self.key_production(key))

        if self._peek(tokens, 'pclass'):
            pclass = self._match(tokens, 'pclass')
            validators.append(self.pclass_production(pclass))

        if self._peek(tokens, 'pclass_func'):
            pclass_func = self._match(tokens, 'pclass_func')
            validators.append(self.pclass_func_production(pclass_func, tokens))

        results = self._eval(validators, self.obj)

        if self._peek(tokens, 'operator'):
            operator = self._match(tokens, 'operator')
            rvals = self.selector_production(tokens)
            if operator == ',':
                results.extend(rvals)
            elif operator == '>':
                results.extend(self.parents(results, rvals))
            elif operator == '~':
                results.extend(self.siblings(results, rvals))
        elif self._peek(tokens, 'empty'):
            self._match(tokens, 'empty')
            rvals = self.selector_production(tokens)
            results.extend(self.ancestors(results, rvals))

        return results

    def parents(self, lhs, rhs):
        pass

    def ancestors(self, lhs, rhs):
        pass

    def parents(self, lhs, rhs):
        pass

    def type_production(self, type_):
        assert type_

        map = {
            'string': basestring,
            'number': numbers.Number,
            'object': collections.Mapping,
            'array': list,
            'boolean': bool,
            'null': type(None)
        }
        return lambda node: isinstance(node.value, map[type_])


    def key_production(self, key):
        assert key

        def validate(node):
            if len(node.parents):
                return node.parents[-1] == key
            return False
        return validate


    def pclass_production(self, pclass):

        if pclass == 'first-child':
            return lambda node: node.sibling_idx == 1
        elif pclass == 'last-child':
            return lambda node: \
                node.siblings and node.sibling_idx == node.siblings
        elif pclass == 'only-child':
            return lambda node: node.siblings == 1
        elif pclass == 'root':
            return lambda node: len(node.parents) == 0
        else:
            raise Exception("unrecognized pclass %s" % pclass)


    def pclass_func_production(self, lexeme, tokens):
        """
        Parse args and pass them to pclass_function_validator.
        """
        if self._peek(tokens, 'operator') == '(':
            self._match(tokens, 'operator')
            args = []

            while tokens:
                if self._peek(tokens, 'operator') == ')':
                    self._match(tokens, 'operator')
                    break
                args.append(tokens.pop(0))
            else:
                raise Exception('syntax error')

            return functools.partial(self.pclass_function_validator, lexeme, args)
        else:
            raise Exception('syntax error')

    def pclass_function_validator(self, pclass, args, node):
        # TODO: DRY this up
        # in arg parsing, should probably use eval
        args = list(args)
        if pclass == 'nth-child':
            if not node.siblings:
                return False
            if self._peek(args, 'word') == 'odd':
                self._match(args, 'word')
                return node.sibling_idx % 2 == 1
            elif self._peek(args, 'word') == 'even':
                return node.sibling_idx % 2 == 0
            elif self._peek(args, 'int'):
                idx = self._match(args, 'int')
                return node.sibling_idx == idx
            else:
                raise Exception('syntax error')
        elif pclass == 'nth-last-child':
            if not node.siblings:
                return False
            reverse_idx = node.siblings - (node.sibling_idx - 1)
            if self._peek(args, 'word') == 'odd':
                self._match(args, 'word')
                return reverse_idx % 2 == 1
            elif self._peek(args, 'word') == 'even':
                return reverse_idx % 2 == 0
            elif self._peek(args, 'int'):
                idx = self._match(args, 'int')
                return reverse_idx == idx
            else:
                raise Exception('syntax error')
        else:
            raise Exception('syntax error')

    def _match(self, tokens, type_):
        if not self._peek(tokens, type_):
            raise Exception('match not successful')

        t = tokens.pop(0)
        return t[1]


    def _peek(self, tokens, type_):
        if not tokens:
            return False
        if tokens[0][0] == type_:
            return tokens[0][1]
        else:
            return False


def select(selector, obj):
    parser = Parser(obj)
    return parser.parse(lex(selector))
