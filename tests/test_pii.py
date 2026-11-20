"""Deteccao e mascaramento de dados pessoais."""

from __future__ import annotations

import pytest

from supportcopilot.guardrails import pii


class TestValidators:
    @pytest.mark.parametrize("value", ["529.982.247-25", "52998224725", "111.444.777-35"])
    def test_valid_cpf(self, value):
        assert pii.valid_cpf(value)

    @pytest.mark.parametrize("value", ["529.982.247-26", "111.111.111-11", "123", "1234567890123"])
    def test_invalid_cpf(self, value):
        assert not pii.valid_cpf(value)

    @pytest.mark.parametrize("value", ["11.222.333/0001-81", "11222333000181"])
    def test_valid_cnpj(self, value):
        assert pii.valid_cnpj(value)

    @pytest.mark.parametrize("value", ["11.222.333/0001-82", "00000000000000", "1122233300018"])
    def test_invalid_cnpj(self, value):
        assert not pii.valid_cnpj(value)

    @pytest.mark.parametrize("value", ["4111 1111 1111 1111", "5500-0000-0000-0004", "340000000000009"])
    def test_valid_card(self, value):
        assert pii.valid_card(value)

    @pytest.mark.parametrize("value", ["4111 1111 1111 1112", "0000000000000000", "1234"])
    def test_invalid_card(self, value):
        assert not pii.valid_card(value)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("200.147.35.149", True), ("8.8.8.8", False), ("192.168.10.1", False), ("10.0.0.7", False)],
    )
    def test_only_public_ips_identify_a_subscriber(self, value, expected):
        assert pii.public_ip(value) is expected

    def test_malformed_ip(self):
        assert not pii.public_ip("999.1.1.1")


class TestRedact:
    @pytest.mark.parametrize(
        ("text", "label", "secret"),
        [
            ("Meu CPF é 529.982.247-25, pode consultar", "CPF", "529.982.247-25"),
            ("CNPJ 11.222.333/0001-81 da empresa", "CNPJ", "11.222.333/0001-81"),
            ("me escreva em joao.silva+suporte@gmail.com", "EMAIL", "joao.silva+suporte@gmail.com"),
            ("meu telefone é (11) 98765-4321", "TELEFONE", "98765-4321"),
            ("ligue para +55 11 91234-5678 amanhã", "TELEFONE", "91234-5678"),
            ("cartão 4111 1111 1111 1111 recusado", "CARTAO", "4111 1111 1111 1111"),
            ("o MAC do aparelho é AA:BB:CC:11:22:33", "MAC", "AA:BB:CC:11:22:33"),
            ("meu IP é 200.147.35.149 hoje", "IP", "200.147.35.149"),
            ("moro no CEP 01310-100", "CEP", "01310-100"),
            ("a senha do wifi é Tucano#2024 e não conecta", "SENHA", "Tucano#2024"),
            ("password: hunter2!", "SENHA", "hunter2!"),
            ("Meu nome é Maria da Silva e preciso de ajuda", "NOME", "Maria da Silva"),
            ("My name is John Smith and the router is down", "NOME", "John Smith"),
            ("MY NAME IS JOHN SMITH", "NOME", "JOHN SMITH"),
            ("minha senha do wifi é 'casa 2024 forte', não conecta", "SENHA", "casa 2024 forte"),
            ("senha=abcd1234", "SENHA", "abcd1234"),
            ("meu celular é 11 9 1234-5678", "TELEFONE", "1234-5678"),
            ("whatsapp 91234-5678", "TELEFONE", "91234-5678"),
            ("meu RG é 12.345.678-9", "RG", "12.345.678-9"),
            ("nasci em 05/03/1990 e sou o titular", "NASCIMENTO", "05/03/1990"),
        ],
    )
    def test_each_type_is_masked(self, text, label, secret):
        result = pii.redact(text)
        assert secret not in result.text
        assert f"[{label}]" in result.text
        assert result.counts[label] == 1

    def test_several_types_in_one_text(self):
        result = pii.redact("Sou o Carlos Souza, CPF 529.982.247-25, email carlos@empresa.com.br, fone (21) 3333-4444")
        assert result.types == ["CPF", "EMAIL", "NOME", "TELEFONE"]
        assert result.total == 4
        assert "Carlos" not in result.text
        assert "529" not in result.text

    @pytest.mark.parametrize(
        "text",
        [
            "Acesse http://192.168.10.1 e use a faixa 192.168.10.100 a 192.168.10.199",
            "O protocolo 123.456.789-00 não é um CPF válido",
            "O roteador tem 4 portas e aceita 64 dispositivos, firmware 1.4.2",
            "Erro E102 no painel, canal 36 com 80 MHz",
            "Como altero a senha do Wi-Fi?",
            "Pedido 4111111111111112 não encontrado",
            "Dimensões 230 x 144 x 37 mm e 410 g",
            "Esqueci a senha do roteador e preciso redefinir",
            "Qual a senha do wifi e como altero?",
            "The password is incorrect after the update",
            "A senha é obrigatória para acessar o painel?",
            "Posso usar o DNS 8.8.8.8 ou o 1.1.1.1?",
            "Atualizei para o firmware 2.1.0.5 e a versão 1.4.2.0 do app",
            "Meu protocolo é 2024123456 e o ticket é #4821937465",
            "protocolo 20912345678 aberto ontem",
            "IMEI 490154203237518 do celular que não conecta",
            "A atualização foi em 05/03/2025",
        ],
    )
    def test_technical_text_is_not_masked(self, text):
        result = pii.redact(text)
        assert result.text == text
        assert result.counts == {}

    def test_overlapping_patterns_resolve_by_priority(self):
        result = pii.redact("contato: 52998224725")
        assert result.counts == {"CPF": 1}

    def test_values_present_in_the_manual_are_kept(self):
        manual = "E-mail: suporte@tucano.example. Telefone: 0800 000 1234."
        answer = "Escreva para suporte@tucano.example [1] ou para fulano@gmail.com."
        result = pii.redact(answer, allowed_in=manual)
        assert "suporte@tucano.example" in result.text
        assert "fulano@gmail.com" not in result.text
        assert result.counts == {"EMAIL": 1}

    def test_empty_text(self):
        assert pii.redact("").text == ""
