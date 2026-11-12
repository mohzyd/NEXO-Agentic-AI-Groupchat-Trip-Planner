(function (C) {
  const socket = C.socket;
  const dialog = document.querySelector('#paymentDialog');
  const form = document.querySelector('#paymentForm');
  const paymentMenuButton = document.querySelector('[data-act="payment"]');
  const budgetInput = form.querySelector('[name="target"]');
  const suggestionButton = document.querySelector('#suggestBudgetBtn');
  const suggestionStatus = document.querySelector('#budgetSuggestionStatus');
  const cards = new Map();
  let leaderUserId = null;
  let isLeader = false;
  let handledReturn = false;

  function showNotice(message) {
    C.addMessage({ type: 'notice', text: message });
  }

  function clearPaymentQuery() {
    const url = new URL(location.href);
    url.searchParams.delete('payment');
    url.searchParams.delete('proposal_id');
    url.searchParams.delete('token');
    history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
  }

  function handlePayPalReturn(data) {
    if (data && typeof data.leaderUserID === 'string') {
      leaderUserId = data.leaderUserID;
      isLeader = C.config.me.id === leaderUserId;
      paymentMenuButton.hidden = !isLeader;
    }
    if (handledReturn) return;
    const params = new URLSearchParams(location.search);
    const payment = params.get('payment');
    if (payment !== 'success' && payment !== 'cancelled') return;
    handledReturn = true;

    if (payment === 'cancelled') {
      const proposalId = params.get('proposal_id');
      const orderId = params.get('token');
      if (proposalId) {
        socket.emit('payment_cancel', {
          proposal_id: proposalId,
          ...(orderId ? { order_id: orderId } : {})
        });
      }
      showNotice('PayPal Sandbox checkout was cancelled.');
    } else {
      const orderId = params.get('token');
      if (orderId) socket.emit('payment_capture', { order_id: orderId });
      else showNotice('PayPal did not return an order ID; the payment was not captured.');
    }

    clearPaymentQuery();
  }

  socket.on('identity', handlePayPalReturn);
  socket.on('payment_error', data => {
    showNotice(data && data.error ? data.error : 'The payment action could not be completed.');
  });
  socket.on('payment_checkout', data => {
    if (!data || typeof data.approval_url !== 'string') {
      showNotice('PayPal Sandbox did not provide a checkout link.');
      return;
    }
    let approvalUrl;
    try {
      approvalUrl = new URL(data.approval_url);
    } catch {
      showNotice('PayPal Sandbox returned an invalid checkout link.');
      return;
    }
    if (approvalUrl.protocol !== 'https:' ||
        !(approvalUrl.hostname === 'sandbox.paypal.com' ||
          approvalUrl.hostname.endsWith('.sandbox.paypal.com'))) {
      showNotice('PayPal Sandbox returned an invalid checkout link.');
      return;
    }
    location.assign(approvalUrl.href);
  });
  socket.on('payment_state', data => {
    if (!data || !Array.isArray(data.proposals)) return;
    leaderUserId = data.leader_user_id || null;
    isLeader = C.config.me.id === leaderUserId;
    paymentMenuButton.hidden = !isLeader;
    data.proposals.forEach(proposal => {
      const nodes = cards.get(proposal.id);
      if (nodes) nodes.forEach(node => paintCard(node, proposal));
    });
  });
  socket.on('budget_suggestion', data => {
    if (!data || typeof data.amount !== 'string' || typeof data.rationale !== 'string') return;
    budgetInput.value = data.amount;
    suggestionStatus.textContent =
      `AI suggestion (${data.currency || 'currency'}): ${data.rationale} You can edit the amount before creating the proposal.`;
    suggestionButton.disabled = false;
    suggestionButton.textContent = 'Suggest budget with AI';
  });
  socket.on('budget_suggestion_error', data => {
    suggestionStatus.textContent = data && data.error
      ? data.error
      : 'Could not suggest a budget. You can enter it manually.';
    suggestionButton.disabled = false;
    suggestionButton.textContent = 'Suggest budget with AI';
  });

  function paintCard(node, proposal) {
    const target = Number(proposal.target);
    const pledged = Number(proposal.pledged);
    const remaining = Math.max(0, target - pledged);
    const progress = node.querySelector('.payment-progress');
    const status = node.querySelector('.payment-status');
    const amountInput = node.querySelector('.payment-pledge-amount');
    const pledgeButton = node.querySelector('.payment-pledge');
    const checkoutButton = node.querySelector('.payment-checkout');
    const myPledge = proposal.pledges_by_user?.[C.config.me.id];
    const myPaymentPending = proposal.pending_user_ids?.includes(C.config.me.id);
    const myPaymentComplete = proposal.paid_user_ids?.includes(C.config.me.id);

    progress.textContent = `${proposal.currency} ${pledged.toFixed(2)} pledged of ${proposal.currency} ${target.toFixed(2)}`;
    if (proposal.status !== 'collecting') {
      progress.textContent += `; ${proposal.currency} ${Number(proposal.paid || 0).toFixed(2)} paid in Sandbox`;
    }
    const statusLabels = {
      collecting: `Still needs ${proposal.currency} ${remaining.toFixed(2)} in simulated pledges.`,
      ready: 'Target fully pledged. Each member pays their own pledge through PayPal Sandbox.',
      paid: 'All pledged contributions were paid in PayPal Sandbox. No real money was charged.'
    };
    status.textContent = statusLabels[proposal.status] || 'This proposal is no longer active.';

    const canPledge = proposal.status === 'collecting';
    amountInput.hidden = !canPledge;
    pledgeButton.hidden = !canPledge;
    if (canPledge) amountInput.value = remaining.toFixed(2);
    checkoutButton.classList.toggle(
      'visible',
      proposal.status === 'ready' && Boolean(myPledge) && !myPaymentComplete
    );
    checkoutButton.disabled = proposal.status !== 'ready' || myPaymentPending;
    checkoutButton.textContent = myPaymentComplete
      ? 'Contribution paid'
      : myPaymentPending
        ? 'Sandbox checkout in progress…'
        : `Pay ${proposal.currency} ${Number(myPledge || 0).toFixed(2)} in Sandbox`;
  }

  C.payments = {
    open() {
      if (!socket.connected) {
        showNotice('Connect to the chat before creating a payment proposal.');
        return;
      }
      if (!isLeader) {
        showNotice('Only the chat leader can create the trip budget proposal.');
        return;
      }
      if (!dialog.open) dialog.showModal();
    },
    mountCard(node, message) {
      if (!node || !message.id) return;
      const nodes = cards.get(message.id) || [];
      nodes.push(node);
      cards.set(message.id, nodes);
      node.querySelector('.payment-pledge').addEventListener('click', () => {
        socket.emit('payment_pledge', {
          proposal_id: message.id,
          amount: node.querySelector('.payment-pledge-amount').value
        });
      });
      node.querySelector('.payment-checkout').addEventListener('click', () => {
        socket.emit('payment_checkout', { proposal_id: message.id });
      });
    }
  };

  document.querySelector('#paymentCancel').addEventListener('click', () => dialog.close());
  suggestionButton.addEventListener('click', () => {
    if (!socket.connected || !isLeader) {
      suggestionStatus.textContent = 'Only the connected chat leader can request an AI budget suggestion.';
      return;
    }
    suggestionButton.disabled = true;
    suggestionButton.textContent = 'Asking AI…';
    suggestionStatus.textContent = 'Reviewing the recent chat and poll results…';
    socket.emit('budget_suggest');
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    const formData = new FormData(form);
    if (!isLeader) {
      showNotice('Only the chat leader can create the trip budget proposal.');
      return;
    }
    socket.emit('payment_propose', {
      title: String(formData.get('title') || '').trim(),
      target: String(formData.get('target') || '')
    });
    form.reset();
    dialog.close();
  });
})(window.Chat);
