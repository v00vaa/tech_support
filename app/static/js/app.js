/**
 * Общие клиентские улучшения интерфейса.
 *
 * Скрипт не содержит бизнес-логики: сервер остаётся источником истины
 * для проверки данных, прав доступа и выполнения операций.
 */

"use strict";

/**
 * Блокирует повторную отправку обычной HTML-формы.
 * Формы с AJAX-обработчиками могут отменить submit через preventDefault().
 */
function handleFormSubmit(event) {
  const form = event.currentTarget;

  if (event.defaultPrevented || form.matches("[data-moderation-form]")) {
    return;
  }

  const submitButtons = form.querySelectorAll(
    'button[type="submit"], input[type="submit"]'
  );

  submitButtons.forEach((button) => {
    button.disabled = true;
    button.setAttribute("aria-disabled", "true");
  });
}

/**
 * Устанавливает обработчики после разбора HTML-документа.
 */
function initializeSupportInterface() {
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", handleFormSubmit);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeSupportInterface, {
    once: true,
  });
} else {
  initializeSupportInterface();
}
