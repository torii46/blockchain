import hashlib
import json
from time import time
from textwrap import dedent
from uuid import uuid4
from urllib.parse import urlparse

from flask import Flask, jsonify, request
import requests


class BlockChain(object):

    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes = set()

        # ジェネシスブロックの生成
        self.new_block(previous_hash=1, proof=100)


    def register_node(self, address):
        """
        ノードリストから新しいノードを追加する

        :param address: <str> ノードのアドレス e.g. 'https://192.168.0.5:5000'
        :return: None
        """

        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)



    def new_block(self, proof, previous_hash=None):
        """
        ブロックチェーンに新しいブロックを生成する

        :param proof: <int> 'Proof' または 'Proof of work' によって与えられる proof
        :param previous_hash: <int> １つ前のブロックのハッシュ
        :return: <dict> 新しいブロック
        """

        block = {
            'index' : len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }

        # 現在のトランザクションリストをリセットする
        self.current_transactions = []

        self.chain.append(block)
        return block
        
        
    def new_transaction(self, sender, recipient, amount):
        """
        次にマイニングされるブロックの新しいトランザクションを生成する 
       
        :param sender: <str> Senderのアドレス
        :param recipient: <str> Recipientのアドレス
        :param amount: <str> 取引額
        :return: <int> 次のトランザクションで利用されることになるインデックス

        """

        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })

        return self.last_block['index'] + 1


    @staticmethod
    def hash(block):
        """
        ブロックの SHA-256 ハッシュを計算する

        :para block: <dict> Block
        :return: <str>
        """

        # ハッシュはキーを辞書順にとった json 文字列からなる
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()


    @property
    def last_block(self):
        return self.chain[-1]

    
    def proof_of_work(self, last_proof):
        """
        シンプルな Proof of Work アルゴリズム：
            - hash(pp') が先頭に4つの0を含むような p' を見つけ出す
            - p は直前の proof, p' は新しい proof

        :param last_proof: <int> 直前のproof
        :return: <int> 
        """
        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1

        return proof


    @staticmethod
    def valid_proof(last_proof, proof):
        """
        Proofのvalidationを行う：hash(last_proof, proof)が先頭に4つの0を含むか？

        :param last_proof: <int> 直前のproof
        :param proof: <int> 現在のproof
        :return: <bool> 
        """

        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"


    def valid_chain(self, chain):
        """
        引数のブロックチェーンが有効かどうか判定する

        :param chain: <list> ブロックチェーン
        :return: <bool>
        """

        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n--------------------\n")
            
            # ブロックのハッシュ値が正しいかチェック
            if block['previous_hash'] != self.hash(last_block):
                return False

            # Proof of Work が正しいかチェック
            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

            last_block = block
            current_index += 1

        return True


    def resolve_conflicts(self):
        """
        コンセンサスアルゴリズム。ネットワークの中の最も長い有効なチェーンで
        このノードのチェーンを置き換えることで衝突を解消する。

        :return: <bool> チェーンが置き換えられたらTrue、そうでないならFalse
        """

        neighbours = self.nodes
        new_chain = None

        max_length = len(self.chain)

        # ノードネットワーク上の全ノードについて、チェーンの妥当性をチェックする
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # チェーンの長さと有効性をチェック
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # このノードが持つチェーンよりも長い新規で有効なチェーンを見つけたら、そのチェーンで置き換える
        if new_chain:
            self.chain = new_chain
            return True

        return False
        

app = Flask(__name__)

# このノードのグローバルユニークなアドレスの生成
node_identifier = str(uuid4()).replace('-', '')

# Blockchain の初期化
blockchain = BlockChain()

@app.route('/mine', methods=['GET'])
def mine():
    # 次の proof を得るために Proof of Work アルゴリズムを走らせる
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # proof を見つけたら 1 コインをゲット
    # sender = "0" は、このノードが新規コインをマインしたことを表す
    blockchain.new_transaction(
        sender = "0",
        recipient = node_identifier,
        amount = 1
    )

    # 新しいブロックの登録のために、チェーンに加える
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'privious_hash': block['previous_hash'],
    }

    return jsonify(response), 200

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()

    # POSTされたデータに、必要なフィールドがあるかチェック
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Missing values', 400

    # 新しいトランザクションを生成
    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 200

@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()

    nodes = values.get('nodes')
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': "New nodes have been added",
        'total_nodes': list(blockchain.nodes),
    }

    return jsonify(response), 200

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain,
        }
    else:
        response = {
            'message': 'Our chain is authoritaive',
            'new_chain': blockchain.chain,
        }

    return jsonify(response), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
                      
