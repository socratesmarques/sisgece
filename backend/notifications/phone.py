import phonenumbers


def normalize_phone(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('Informe um telefone válido com DDD.')
    try:
        number = phonenumbers.parse(value, 'BR')
        if number.extension or not phonenumbers.is_valid_number(number):
            raise ValueError()
        return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    except (phonenumbers.NumberParseException, ValueError):
        raise ValueError('Informe um telefone válido com DDD.') from None


def masked(value):
    return '•••• ' + value[-4:]
