-- Migration 012: renombrar la identidad del superadmin a un email de-brandeado.
-- Idempotente: no-op si la cuenta antigua ya no existe.

-- 1. Renombrar la cuenta superadmin existente (mismo id/password/rol/contenido).
--    El trigger de 004 permite cambiar el email (solo bloquea role/is_active/DELETE).
UPDATE users SET email = 'pgg@pgg.pgg'
WHERE lower(email) = 'patxigg@biklabs.ai';

-- 2. Actualizar el trigger de protección para que apunte al nuevo email.
CREATE OR REPLACE FUNCTION protect_superadmin_account()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF lower(OLD.email) = 'pgg@pgg.pgg' THEN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Cannot delete the protected superadmin account';
        END IF;
        IF NEW.role != OLD.role OR NEW.is_active != OLD.is_active THEN
            RAISE EXCEPTION 'Cannot modify role or active status of the protected superadmin account';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;
