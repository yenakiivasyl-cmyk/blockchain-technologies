import pytest

from aidchain import views
from aidchain.crypto import KeyPair, sha256
from aidchain.demo import build_demo, doc_hash
from aidchain.ledger import Block, RuleViolation, Transaction, validate_chain
from aidchain.merkle import merkle_proof, merkle_root, verify_proof


@pytest.fixture(scope="module")
def demo():
    return build_demo()


def fresh():
    return build_demo()


def addr_by_name(net, name):
    state = net.reference_node().audit()["state"]
    return next(a for a, x in state.actors.items() if x["name"] == name)


def test_merkle_proof_for_every_leaf():
    leaves = [sha256(str(i)) for i in range(7)]
    root = merkle_root(leaves)
    for i, leaf in enumerate(leaves):
        assert verify_proof(leaf, merkle_proof(leaves, i), root)
    assert not verify_proof(sha256("x"), merkle_proof(leaves, 0), root)


def test_transaction_signature_binds_payload():
    keys = KeyPair.generate()
    tx = Transaction.create(keys, "REGISTER", {"name": "A", "role": "DONOR"})
    assert tx.signature_ok()
    tx.payload["name"] = "B"
    assert not tx.signature_ok()


def test_demo_chain_is_valid_and_consistent(demo):
    tips = {n.tip.hash for n in demo.nodes.values()}
    assert len(tips) == 1
    for node in demo.nodes.values():
        assert node.audit()["ok"]
        assert node.tip.hash.startswith("0000")


def test_campaign_accounting(demo):
    state = demo.reference_node().audit()["state"]
    gens = next(c for c in state.campaigns.values() if c["title"].startswith("Генератори"))
    assert gens["raised"] == 195_000 and gens["spent"] == 189_000


def test_trace_donation(demo):
    state = demo.reference_node().audit()["state"]
    donation = next(d for d in state.donations.values() if d["amount"] == 150_000)
    trace = views.trace_donation(state, donation["id"])
    assert trace["steps"][0]["receipt"]["status"] == "OK"
    assert trace["used"] + trace["unused"] == 150_000


def test_document_verification(demo):
    ref = demo.reference_node()
    state = ref.audit()["state"]
    ok = views.verify_document(ref.chain, state, doc_hash("invoice_drones.txt"))
    assert ok["found"] and ok["proof"]["verified"]
    forged = views.verify_document(ref.chain, state, doc_hash("invoice_drones_FORGED.txt"))
    assert not forged["found"]


def test_overspending_rejected():
    net = fresh()
    fund = addr_by_name(net, "БФ «Світанок»")
    supplier = addr_by_name(net, "ТОВ «МедПостач»")
    state = net.reference_node().audit()["state"]
    ifak = next(c for c in state.campaigns.values() if c["title"].startswith("Тактичні"))
    with pytest.raises(RuleViolation):
        net.submit(fund, "PURCHASE", {"campaign": ifak["id"], "supplier": supplier,
                                      "items": [{"name": "IFAK", "qty": 1000, "price": 1000}]})


def test_only_recipient_can_confirm_receipt():
    net = fresh()
    state = net.reference_node().audit()["state"]
    shipment = next(s for s in state.shipments.values() if not s["receipt"])
    stranger = addr_by_name(net, "Олена Коваль")
    with pytest.raises(RuleViolation):
        net.submit(stranger, "RECEIPT", {"shipment": shipment["id"], "status": "OK"})


@pytest.mark.parametrize("remine", [False, True])
def test_tampering_detected_and_healed_by_consensus(remine):
    net = fresh()
    net.tamper("lviv", 3, remine=remine)
    audit = net.nodes["lviv"].audit()
    assert not audit["ok"] and audit["first_bad"] == 3
    assert not audit["blocks"][2]["checks"]["tx_signatures"]
    assert net.consensus("lviv")
    assert net.nodes["lviv"].audit()["ok"]
    assert net.nodes["lviv"].tip.hash == net.nodes["kyiv"].tip.hash


def test_fork_resolution_longest_chain_wins():
    net = fresh()
    net.set_online("cv", False)
    net.mine("cv")  # cv має донат у mempool -> власний блок офлайн
    olena = addr_by_name(net, "Олена Коваль")
    state = net.reference_node().audit()["state"]
    campaign = next(iter(state.campaigns))
    net.submit(olena, "DONATION", {"campaign": campaign, "amount": 1_000})
    net.mine("kyiv")
    net.submit(olena, "DONATION", {"campaign": campaign, "amount": 2_000})
    net.mine("kyiv")
    net.set_online("cv", True)
    assert net.nodes["cv"].tip.hash == net.nodes["kyiv"].tip.hash


def test_persistence_roundtrip(tmp_path, demo):
    demo.path = tmp_path / "state.json"
    demo.save()
    from aidchain.network import Network
    loaded = Network.load(demo.path)
    assert loaded.nodes["kyiv"].tip.hash == demo.nodes["kyiv"].tip.hash
    assert validate_chain(loaded.nodes["kyiv"].chain)["ok"]
    assert Block.genesis().hash == loaded.nodes["kyiv"].chain[0].hash
