-- Entradas recebidas passam a aguardar a decisão da coordenação.
-- Aprovar uma solicitação não registra a entrada física no campus.
UPDATE solicitacoes SET status='PENDENTE'
WHERE tipo='Entrada' AND status='RECEBIDA';
