#!/usr/bin/env python3
"""Exercise WeiBudget through a funded Fe wallet on a disposable local chain."""

import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = 86_400
MIDNIGHT = 20_000 * DAY


def demonstrate(ipc, artifacts):
    def rpc(method, *params):
        request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(5)
            client.connect(str(ipc))
            client.sendall(json.dumps(request).encode() + b"\n")
            with client.makefile("rb") as stream:
                response = json.loads(stream.readline())
        if "error" in response:
            raise RuntimeError(f"{method}: {response['error']}")
        return response["result"]

    def calldata(signature, *arguments):
        selector = rpc("web3_sha3", "0x" + signature.encode().hex())[:10]
        return selector + "".join(f"{value:064x}" for value in arguments)

    def transact(sender, data, *, to=None, value=0, expect_success=True):
        tx = {"from": sender, "data": data, "value": hex(value), "gas": hex(2_000_000)}
        if to:
            tx["to"] = to
        tx_hash = rpc("eth_sendTransaction", tx)
        deadline = time.monotonic() + 10
        receipt = rpc("eth_getTransactionReceipt", tx_hash)
        while receipt is None:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Local Anvil did not mine {tx_hash}")
            time.sleep(0.05)
            receipt = rpc("eth_getTransactionReceipt", tx_hash)
        if (int(receipt["status"], 16) == 1) != expect_success:
            raise RuntimeError(f"Unexpected transaction receipt: {receipt}")
        return receipt

    owner, agent, recipient = rpc("eth_accounts")
    # This third account only receives ETH and never pays gas during the demo.
    rpc("anvil_setBalance", recipient, "0x0")

    def deploy(name, arguments=""):
        code = (artifacts / f"{name}.bin").read_text().strip().removeprefix("0x")
        return transact(owner, "0x" + code + arguments)["contractAddress"]

    wallet = deploy("ReferenceWallet", f"{int(agent, 16):064x}")
    rejecting = deploy("RejectingReceiver")

    def read_state():
        balances = [int(rpc("eth_getBalance", addr, "latest"), 16)
                    for addr in (wallet, recipient, rejecting)]
        remaining = rpc("eth_call", {"to": wallet, "data": calldata("remaining()")}, "latest")
        return (*balances, int(remaining, 16))

    previous = read_state()
    if previous != (0, 0, 0, 0):
        raise RuntimeError(f"Expected empty contracts and recipient at deployment; read {previous}")

    def check(label, expected):
        nonlocal previous
        actual = read_state()
        if actual != expected:
            raise RuntimeError(f"{label}: expected {expected} wei; read {actual}")
        delta = [f"{before} -> {after}" for before, after in zip(previous, actual)]
        print(f"{label:<36} " + " ".join(f"{value:>11}" for value in delta))
        previous = actual

    def pay(to, amount, succeeds=True):
        transact(agent, calldata("pay(address,uint256)", int(to, 16), amount),
                 to=wallet, expect_success=succeeds)

    print(f"{'Transaction or block (wei)':<36} {'Wallet':>11} {'Recipient':>11} {'Rejector':>11} {'Allowance':>11}")
    transact(owner, calldata("deposit()"), to=wallet, value=20)
    check("Wallet funded", (20, 0, 0, 0))
    transact(owner, calldata("setLimit(uint256)", 10), to=wallet)
    check("Owner grants 10", (20, 0, 0, 10))
    pay(recipient, 6)
    check("Pay 6 to recipient", (14, 6, 0, 4))
    pay(rejecting, 3, succeeds=False)
    check("Rejector refuses 3: reverted", (14, 6, 0, 4))
    transact(owner, calldata("revoke()"), to=wallet)
    check("Owner revokes", (14, 6, 0, 0))
    pay(recipient, 1, succeeds=False)
    check("Pay 1 after revocation: reverted", (14, 6, 0, 0))
    transact(owner, calldata("setLimit(uint256)", 10), to=wallet)
    check("Same-day regrant of 10", (14, 6, 0, 4))
    pay(recipient, 4)
    check("Pay remaining 4 to recipient", (10, 10, 0, 0))
    pay(recipient, 1, succeeds=False)
    check("Exceed limit by 1: reverted", (10, 10, 0, 0))

    rpc("evm_setNextBlockTimestamp", MIDNIGHT + DAY)
    rpc("evm_mine")
    check("Next UTC midnight", (10, 10, 0, 10))
    pay(recipient, 3)
    check("Pay 3 to recipient", (7, 13, 0, 7))


def main():
    # A short path keeps the Unix socket name below the macOS and Linux limits.
    with tempfile.TemporaryDirectory(prefix="weibudget-", dir="/tmp") as directory:
        temp = Path(directory)
        subprocess.run(
            ["fe", "build", "--emit", "bytecode", "--out-dir", directory],
            cwd=ROOT, check=True,
        )
        ipc = temp / "anvil.ipc"
        command = [
            "anvil", "--host", "127.0.0.1", "--port", "0", "--ipc", str(ipc),
            "--mnemonic-random", "--accounts", "3", "--timestamp", str(MIDNIGHT + DAY // 2),
            "--quiet",
        ]
        with subprocess.Popen(command, cwd=temp, stdout=subprocess.DEVNULL) as chain:
            try:
                deadline = time.monotonic() + 10
                while not ipc.exists():
                    if chain.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Local Anvil did not start")
                    time.sleep(0.05)
                demonstrate(ipc, temp)
            finally:
                chain.terminate()


if __name__ == "__main__":
    main()
