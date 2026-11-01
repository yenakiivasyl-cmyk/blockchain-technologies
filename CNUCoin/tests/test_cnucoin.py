import pytest

from cnucoin import crypto, db, members, mining, transactions, validator


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def people(conn):
    alice = members.register(conn, "Alice", initial_cents=10_000)
    bob = members.register(conn, "Bob", initial_cents=5_000)
    miner = members.register(conn, "Miner", is_miner=True)
    return alice["CNUCoinID"], bob["CNUCoinID"], miner["CNUCoinID"]


def test_address_is_hash_of_public_key(conn):
    m = members.register(conn, "Carol")
    assert m["CNUCoinID"] == crypto.sha256(m["PublicKey"])
    assert len(m["CNUCoinID"]) == 64


def test_signature_roundtrip():
    priv, pub = crypto.generate_keypair()
    sig = crypto.sign(priv, "hello")
    assert crypto.verify(pub, "hello", sig)
    assert not crypto.verify(pub, "hell0", sig)


def test_first_transaction_uses_genesis_zeros(conn, people):
    alice, bob, _ = people
    tx = transactions.create_transaction(conn, alice, bob, 2_500)
    assert tx["ChainHash"] == "0" * 64 and tx["ChainNonce"] == 0
    assert tx["TAHash"] == crypto.sha256(tx["Payload"])
    row = conn.execute("SELECT * FROM BlockChainTable WHERE TAID = ?", (tx["TAID"],)).fetchone()
    assert row["BlockChainHash"] == tx["TAHash"] and row["IsMined"] == 0


def test_cannot_overspend_including_pending(conn, people):
    alice, bob, _ = people
    transactions.create_transaction(conn, alice, bob, 8_000)
    with pytest.raises(transactions.TransactionError):
        transactions.create_transaction(conn, alice, bob, 3_000)


def test_non_miner_cannot_mine(conn, people):
    alice, bob, _ = people
    transactions.create_transaction(conn, alice, bob, 100)
    with pytest.raises(mining.MiningError):
        mining.mine_next(conn, alice)


def test_mining_moves_funds_and_locks_until_next_block(conn, people):
    alice, bob, miner = people
    transactions.create_transaction(conn, alice, bob, 2_000)
    result = mining.mine_next(conn, miner)
    assert result["BlockChainHash"].startswith("0")
    assert members.balances(conn, alice)["total"] == 8_000
    bob_bal = members.balances(conn, bob)
    assert bob_bal["total"] == 7_000 and bob_bal["locked"] == 2_000
    assert members.balances(conn, miner)["total"] == 100  # 5 % винагороди

    transactions.create_transaction(conn, alice, bob, 1_000)
    second = mining.mine_next(conn, miner)
    assert second["ConfirmedBlockID"] == result["BlockID"]
    assert members.balances(conn, bob)["locked"] == 1_000


def test_higher_difficulty(conn, people):
    alice, bob, miner = people
    transactions.create_transaction(conn, alice, bob, 100)
    result = mining.mine_next(conn, miner, difficulty=3)
    assert result["BlockChainHash"].startswith("000")


def test_validator_detects_tampering(conn, people):
    alice, bob, miner = people
    for amount in (1_000, 2_000):
        transactions.create_transaction(conn, alice, bob, amount)
        mining.mine_next(conn, miner)
    assert validator.validate_chain(conn)["ok"]

    conn.execute("UPDATE TransactionsTable SET TASum = 999999 WHERE TAID = 1")
    report = validator.validate_chain(conn)
    assert not report["ok"]
    assert report["blocks"][0]["checks"]["tx_hash"] is False


def test_validator_detects_broken_link(conn, people):
    alice, bob, miner = people
    for amount in (1_000, 2_000):
        transactions.create_transaction(conn, alice, bob, amount)
        mining.mine_next(conn, miner)
    conn.execute("UPDATE BlockChainTable SET BlockChainHash = ? WHERE BlockID = 1", ("0" * 64,))
    report = validator.validate_chain(conn)
    assert not report["blocks"][0]["checks"]["pow"]
    assert not report["blocks"][1]["checks"]["link"]
