"use strict";

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + "=")) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function parseJsonScriptElement(id, fallback = {}) {
    const el = document.getElementById(id);
    if (!el || !el.textContent) return fallback;
    try {
        return JSON.parse(el.textContent);
    } catch (error) {
        console.error(`Invalid JSON in #${id}`, error);
        return fallback;
    }
}

function initExcursionDetailPage() {
    const csrftoken = getCookie("csrftoken");
    const userRole = getCookie("user_role") ? getCookie("user_role") : "";
    const userId = getCookie("user_id") ? getCookie("user_id") : "";

    const availableDatesByRegion = parseJsonScriptElement("available-dates-json", {});
    const pickupPointsByRegion = parseJsonScriptElement("pickup-points-json", {});
    const regionAvailabilityMap = parseJsonScriptElement("region-availability-map-json", {});

    const regionSelect = document.getElementById("regions");
    const pickupPointSelect = document.getElementById("pickup-point");
    const datePickerInput = document.getElementById("date-picker");
    const availabilityIdInput = document.getElementById("availability-id");
    const notAvailability = document.querySelector(".not-availability");
    const bookingForm = document.getElementById("booking-form");
    const formErrors = document.getElementById("form-errors");
    const guestNameInput = document.querySelector("#guest-name");
    const guestEmailInput = document.querySelector("#guest-email");

    let picker = null;
    let currentAvailability = null;

    function calculateTotal() {
        const adults = parseInt(document.querySelector('input[name="adults"]').value) || 0;
        const children = parseInt(document.querySelector('input[name="children"]').value) || 0;
        const infants = parseInt(document.querySelector('input[name="infants"]').value) || 0;
        const availabilityId = availabilityIdInput.value;

        if (!availabilityId) {
            document.getElementById("total-price").textContent = "0.00";
            document.getElementById("total-price-input").value = 0;
            return;
        }

        const adultPrice = parseFloat(document.querySelector(`input[name="${availabilityId}-adult-price"]`)?.value || 0);
        const childPrice = parseFloat(document.querySelector(`input[name="${availabilityId}-child-price"]`)?.value || 0);
        const infantPrice = parseFloat(document.querySelector(`input[name="${availabilityId}-infant-price"]`)?.value || 0);

        const total = (adults * adultPrice) + (children * childPrice) + (infants * infantPrice);
        document.getElementById("total-price").textContent = total.toFixed(2);
        document.getElementById("total-price-input").value = total;
    }

    function displayRegionDetails(regionId) {
        const adultPriceEl = document.getElementById("adult-price");
        const childPriceEl = document.getElementById("child-price");
        const infantPriceEl = document.getElementById("infant-price");
        const selectedRegionNameEl = document.getElementById("selected-region-name");
        const pickupPointsDisplayEl = document.getElementById("pickup-points-display");
        const regionPickupTime = document.querySelector(".region-pickup-time");

        if (!regionId) {
            if (adultPriceEl) adultPriceEl.textContent = "0.00";
            if (childPriceEl) childPriceEl.textContent = "0.00";
            if (infantPriceEl) infantPriceEl.textContent = "0.00";
            if (selectedRegionNameEl) selectedRegionNameEl.textContent = "Please select a region";
            if (pickupPointsDisplayEl) {
                pickupPointsDisplayEl.innerHTML = '<div class="flex flex-col gap-2"><p class="text-sm text-gray-500">Select a region to view pickup points</p></div>';
                regionPickupTime.textContent = "";
            }
            return;
        }

        const availabilities = regionAvailabilityMap[regionId];
        if (availabilities && availabilities.length > 0) {
            currentAvailability = availabilities[0];

            regionPickupTime.textContent = `Pickup time: ${currentAvailability.pickup_start_time} - ${currentAvailability.pickup_end_time}`;

            if (adultPriceEl) adultPriceEl.textContent = currentAvailability.adult_price.toFixed(2);
            if (childPriceEl) childPriceEl.textContent = currentAvailability.child_price.toFixed(2);
            if (infantPriceEl) infantPriceEl.textContent = currentAvailability.infant_price.toFixed(2);

            const regionOption = regionSelect.querySelector(`option[value="${regionId}"]`);
            if (selectedRegionNameEl && regionOption) {
                selectedRegionNameEl.textContent = regionOption.textContent;
            }

            if (pickupPointsDisplayEl && currentAvailability.pickup_points) {
                let pickupPointsHTML = '<div class="flex flex-col gap-2"><ul class="pickup-points-list">';

                currentAvailability.pickup_points.forEach((point) => {
                    pickupPointsHTML += `
                        <li>
                            <div class="flex items-center py-1">
                                <svg class="mr-2" width="17" height="19" viewBox="0 0 20 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M9.75 23C14.125 18.6 18.5 14.66 18.5 9.8C18.5 4.93989 14.5825 1 9.75 1C4.91751 1 1 4.93989 1 9.8C1 14.66 5.375 18.6 9.75 23Z" stroke="#8E24AA" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                    <path d="M9.75 13.2222C11.8211 13.2222 13.5 11.5806 13.5 9.55552C13.5 7.53048 11.8211 5.88885 9.75 5.88885C7.67887 5.88885 6 7.53048 6 9.55552C6 11.5806 7.67887 13.2222 9.75 13.2222Z" stroke="#8E24AA" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                </svg>
                                <a href="#">${point.name}</a>
                            </div>
                        </li>
                    `;
                });

                pickupPointsHTML += "</ul></div>";
                pickupPointsDisplayEl.innerHTML = pickupPointsHTML;
            }
        }
    }

    function updatePickupPoints(regionId) {
        pickupPointSelect.innerHTML = '<option value="">Select a pickup point</option>';

        if (!regionId) {
            pickupPointSelect.disabled = true;
            return;
        }

        const pickupPoints = pickupPointsByRegion[regionId];
        if (pickupPoints && pickupPoints.length > 0) {
            const sortedPoints = [...pickupPoints].sort((a, b) => a.name.localeCompare(b.name));
            sortedPoints.forEach((point) => {
                const option = document.createElement("option");
                option.value = point.id;
                option.textContent = point.name;
                pickupPointSelect.appendChild(option);
            });
            pickupPointSelect.disabled = false;
        } else {
            pickupPointSelect.disabled = true;
            console.log("No pickup points found for region:", regionId);
        }
    }

    function updateDatePicker(regionId) {
        const availableDates = availableDatesByRegion[regionId] || [];
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const futureAvailableDates = availableDates.filter((item) => {
            const itemDate = new Date(item.date);
            return itemDate >= today;
        });

        if (picker) {
            picker.destroy();
            picker = null;
        }

        datePickerInput.value = "";
        availabilityIdInput.value = "";

        if (futureAvailableDates.length > 0) {
            picker = flatpickr(datePickerInput, {
                enable: futureAvailableDates.map((item) => item.date),
                dateFormat: "Y-m-d",
                minDate: "today",
                disableMobile: false,
                clickOpens: true,
                allowInput: false,
                static: false,
                onChange: function (selectedDates, dateStr) {
                    const selectedDate = futureAvailableDates.find((item) => item.date === dateStr);
                    if (selectedDate && selectedDate.availability_id) {
                        availabilityIdInput.value = selectedDate.availability_id;
                        calculateTotal();
                    }
                },
                onReady: function (selectedDates, dateStr, instance) {
                    console.log("Flatpickr ready with", futureAvailableDates.length, "available dates");
                }
            });

            datePickerInput.placeholder = "Click to select a date";
            datePickerInput.disabled = false;
        } else {
            datePickerInput.placeholder = "No available dates for this region";
            datePickerInput.disabled = true;
        }
    }

    function markGuestFieldsAsSystemAutofilled() {
        if (guestNameInput) guestNameInput.dataset.systemAutofilled = "true";
        if (guestEmailInput) guestEmailInput.dataset.systemAutofilled = "true";
    }

    function showInlineError(inputEl, message) {
        if (!inputEl) return;
        let nextEl = inputEl.nextElementSibling;
        while (nextEl && nextEl.classList && nextEl.classList.contains("text-red-600")) {
            const toRemove = nextEl;
            nextEl = nextEl.nextElementSibling;
            toRemove.remove();
        }
        inputEl.classList.add("border-red-500");
        const errorDiv = document.createElement("p");
        errorDiv.className = "mt-1 text-sm text-red-600";
        errorDiv.textContent = message;
        inputEl.insertAdjacentElement("afterend", errorDiv);
    }

    function initDeleteExcursion() {
        const deleteExcursionBtn = document.getElementById("delete-excursion-btn");
        const deleteExcursionForm = document.getElementById("delete-ex-form");

        if (deleteExcursionBtn && deleteExcursionForm) {
            deleteExcursionBtn.addEventListener("click", function (e) {
                e.preventDefault();
                const titleEl = document.querySelector(".excursion-title");
                const excursionTitle = titleEl ? titleEl.textContent.trim() : "this excursion";
                Swal.fire({
                    title: "Are you sure?",
                    text: `Do you want to delete excursion "${excursionTitle}"?`,
                    icon: "warning",
                    showCancelButton: true,
                    confirmButtonColor: "#d33",
                    cancelButtonColor: "#3085d6",
                    confirmButtonText: "Yes, delete it!"
                }).then((result) => {
                    if (result.isConfirmed) {
                        deleteExcursionForm.submit();
                    }
                });
            });
        }
    }

    function initGalleryLightbox() {
        const galleryItems = document.querySelectorAll(".gallery-item");
        const mainImage = document.querySelector(".main-image");
        const lightbox = document.getElementById("gallery-lightbox");
        const lightboxImage = document.getElementById("lightbox-image");
        const lightboxCaption = document.getElementById("lightbox-caption");
        const lightboxCounter = document.getElementById("lightbox-counter");
        const closeLightbox = document.getElementById("close-lightbox");
        const prevImage = document.getElementById("prev-image");
        const nextImage = document.getElementById("next-image");

        let currentImageIndex = 0;
        const images = [];

        if (mainImage) {
            images.push({
                url: mainImage.dataset.imageUrl,
                alt: mainImage.dataset.alt || ""
            });
        }

        Array.from(galleryItems).forEach((item) => {
            images.push({
                url: item.dataset.imageUrl,
                alt: item.dataset.alt || ""
            });
        });

        function showLightbox(index) {
            if (images.length === 0) return;

            currentImageIndex = index;
            lightboxImage.src = images[index].url;
            lightboxImage.alt = images[index].alt;
            lightboxCaption.textContent = images[index].alt;
            lightboxCounter.textContent = `${index + 1} / ${images.length}`;
            lightbox.classList.remove("hidden");
            document.body.style.overflow = "hidden";
        }

        function hideLightbox() {
            lightbox.classList.add("hidden");
            document.body.style.overflow = "auto";
        }

        function showNextImage() {
            currentImageIndex = (currentImageIndex + 1) % images.length;
            showLightbox(currentImageIndex);
        }

        function showPrevImage() {
            currentImageIndex = (currentImageIndex - 1 + images.length) % images.length;
            showLightbox(currentImageIndex);
        }

        if (mainImage) {
            mainImage.addEventListener("click", () => showLightbox(0));
        }

        galleryItems.forEach((item, index) => {
            item.addEventListener("click", () => {
                showLightbox(index + 1);
            });
        });

        if (closeLightbox) {
            closeLightbox.addEventListener("click", hideLightbox);
        }

        if (prevImage) {
            prevImage.addEventListener("click", showPrevImage);
        }

        if (nextImage) {
            nextImage.addEventListener("click", showNextImage);
        }

        document.addEventListener("keydown", (e) => {
            if (lightbox && !lightbox.classList.contains("hidden")) {
                switch (e.key) {
                    case "Escape":
                        hideLightbox();
                        break;
                    case "ArrowLeft":
                        showPrevImage();
                        break;
                    case "ArrowRight":
                        showNextImage();
                        break;
                }
            }
        });

        if (lightbox) {
            lightbox.addEventListener("click", (e) => {
                if (e.target === lightbox) {
                    hideLightbox();
                }
            });
        }
    }

    function initBookingForm() {
        if (pickupPointSelect) pickupPointSelect.disabled = true;
        if (datePickerInput) {
            datePickerInput.disabled = true;
            datePickerInput.placeholder = "Select a region first";
        }

        if (regionSelect) {
            regionSelect.addEventListener("change", function () {
                const regionId = this.value;
                displayRegionDetails(regionId);
                updatePickupPoints(regionId);
                updateDatePicker(regionId);
                calculateTotal();
            });
        }

        if (!notAvailability && bookingForm) {
            if (userRole == "client") {
                console.log("userRole: " + userRole);
                console.log("userId: " + userId);
                fetch("/get_user_details/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrftoken
                    }
                })
                    .then((response) => response.json())
                    .then((data) => {
                        console.log("User profile data:", data.user_profile);
                        document.querySelector("#guest-name").value = data.user_profile.name;
                        document.querySelector("#guest-email").value = data.user_profile.email;
                        document.querySelector("#guest-email").disabled = true;
                        document.querySelector("#guest-email-disabled").classList.remove("hidden");
                        markGuestFieldsAsSystemAutofilled();
                    })
                    .catch((error) => {
                        console.error("Error:", error);
                    });
            }

            function checkVoucher() {
                const voucherInput = getCookie("voucher_code");
                if (voucherInput) {
                    fetch("/check_voucher/", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            "X-CSRFToken": getCookie("csrftoken")
                        },
                        body: JSON.stringify({
                            voucher_code: voucherInput
                        })
                    })
                        .then((response) => {
                            if (!response.ok) {
                                throw new Error(`HTTP error! status: ${response.status}`);
                            }
                            const contentType = response.headers.get("content-type");
                            if (!contentType || !contentType.includes("application/json")) {
                                throw new Error("Response is not JSON");
                            }
                            return response.json();
                        })
                        .then((data) => {
                            if (data.success) {
                                document.querySelector("#guest-name").value = data.return_data.client_name;
                                document.querySelector("#guest-email").value = data.return_data.client_email;
                                markGuestFieldsAsSystemAutofilled();

                                if (data.return_data.pickup_point_id) {
                                    setTimeout(() => {
                                        const pickupPointOption = pickupPointSelect.querySelector(`option[value="${data.return_data.pickup_point_id}"]`);
                                        if (pickupPointOption) {
                                            pickupPointSelect.value = data.return_data.pickup_point_id;
                                        }
                                    }, 100);
                                }
                            } else {
                                console.log("Voucher check failed:", data.message);
                            }
                        })
                        .catch((error) => {
                            console.error("Voucher check error:", error.message);
                        });
                }
            }

            checkVoucher();

            function autoSelectUserPickupPoint() {
                const userPickupPointId = document.getElementById("user-pickup-point-id")?.value;
                const userRegionId = document.getElementById("user-region-id")?.value;

                if (userPickupPointId && userRegionId) {
                    console.log("Auto-selecting user pickup point:", userPickupPointId, "in region:", userRegionId);
                    regionSelect.value = userRegionId;
                    displayRegionDetails(userRegionId);
                    updatePickupPoints(userRegionId);
                    updateDatePicker(userRegionId);

                    setTimeout(() => {
                        const pickupPointOption = pickupPointSelect.querySelector(`option[value="${userPickupPointId}"]`);
                        if (pickupPointOption) {
                            pickupPointSelect.value = userPickupPointId;
                            console.log("User pickup point auto-selected successfully");
                        } else {
                            console.log("User pickup point not found in dropdown");
                        }
                    }, 100);
                }
            }

            setTimeout(autoSelectUserPickupPoint, 200);
            calculateTotal();

            document.querySelectorAll('input[type="number"]').forEach((input) => {
                input.addEventListener("change", calculateTotal);
                input.addEventListener("input", calculateTotal);
            });

            datePickerInput.addEventListener("change", calculateTotal);

            document.querySelector("#clear-numbers").addEventListener("click", function (e) {
                e.preventDefault();

                const keepGuestName = guestNameInput && guestNameInput.dataset.systemAutofilled === "true";
                const keepGuestEmail = guestEmailInput && guestEmailInput.dataset.systemAutofilled === "true";
                const preservedGuestName = keepGuestName ? guestNameInput.value : "";
                const preservedGuestEmail = keepGuestEmail ? guestEmailInput.value : "";

                if (regionSelect) regionSelect.value = "";
                displayRegionDetails("");
                updatePickupPoints("");
                updateDatePicker("");
                if (pickupPointSelect) pickupPointSelect.value = "";
                if (availabilityIdInput) availabilityIdInput.value = "";

                bookingForm.querySelectorAll('input[type="number"]').forEach((input) => {
                    input.value = 0;
                });

                bookingForm.querySelectorAll('input[type="text"], input[type="email"], textarea').forEach((input) => {
                    if ((keepGuestName && input.id === "guest-name") || (keepGuestEmail && input.id === "guest-email")) {
                        return;
                    }
                    input.value = "";
                });
                bookingForm.querySelectorAll("select").forEach((select) => {
                    select.selectedIndex = 0;
                });

                if (keepGuestName && guestNameInput) guestNameInput.value = preservedGuestName;
                if (keepGuestEmail && guestEmailInput) guestEmailInput.value = preservedGuestEmail;

                calculateTotal();
            });

            if (document.querySelector("#partial-payment")) {
                document.querySelector("#partial-payment").addEventListener("change", function (e) {
                    e.preventDefault();
                    const partialPayment = document.querySelector("#partial-payment").value;
                    const total = document.querySelector("#total-price").textContent;

                    if (partialPayment <= 0) {
                        document.querySelector(".remaining-price-div").classList.add("hidden");
                        document.querySelector("#partial-paid-method-div").classList.add("hidden");
                        return;
                    }

                    const remaining = total - partialPayment;
                    document.querySelector(".remaining-price-div").classList.remove("hidden");
                    document.querySelector("#remaining-price").textContent = remaining.toFixed(2);
                    document.querySelector("#partial-paid-method-div").classList.remove("hidden");
                });
            }

            bookingForm.addEventListener("submit", function (e) {
                e.preventDefault();

                const submitButton = document.getElementById("submit-button");
                const loadingSpinner = document.getElementById("loading-spinner");
                const submitText = document.getElementById("submit-text");

                submitButton.disabled = true;
                loadingSpinner.classList.remove("hidden");
                submitText.textContent = "Processing...";

                if (formErrors) {
                    formErrors.classList.add("hidden");
                    const errorList = formErrors.querySelector("ul");
                    if (errorList) {
                        errorList.innerHTML = "";
                    }
                }

                document.querySelectorAll(".border-red-500").forEach((el) => el.classList.remove("border-red-500"));
                document.querySelectorAll(".text-red-600").forEach((el) => {
                    if (el.tagName === "P" && el.classList.contains("text-red-600")) {
                        el.remove();
                    }
                });

                const selectedDate = datePickerInput.value.trim();
                const availabilityId = availabilityIdInput.value.trim();
                const regionId = regionSelect.value;
                const pickupPointId = pickupPointSelect.value;
                const adults = parseInt(document.querySelector('input[name="adults"]').value) || 0;
                const guestEmail = document.querySelector("#guest-email").value.trim();
                const guestName = document.querySelector("#guest-name").value.trim();
                const phoneCountry = document.querySelector("#phone-country").value.trim();
                const phoneNumber = document.querySelector("#phone-number").value.trim();
                const voucherInput = document.querySelector("#voucher_code");
                const voucherCode = (voucherInput && voucherInput.value) ? voucherInput.value.trim() : "";
                const partialPaymentInput = document.querySelector("#partial-payment");
                const partialPayment = (partialPaymentInput && partialPaymentInput.value) ? partialPaymentInput.value.trim() : "";
                const partialPaidMethodInput = document.querySelector("#partial-paid-method");
                const partialPaidMethod = (partialPaidMethodInput && partialPaidMethodInput.value) ? partialPaidMethodInput.value.trim() : "";

                let errors = [];
                const addValidationError = (field, inputEl, message) => {
                    errors.push({ field, message });
                    showInlineError(inputEl, message);
                };

                if (!regionId) {
                    addValidationError("regions", regionSelect, "Please select a region.");
                }

                if (!pickupPointId) {
                    addValidationError("pickup_point", pickupPointSelect, "Please select a pickup point.");
                }

                if (!selectedDate || !availabilityId) {
                    addValidationError("date", datePickerInput, "Please select a date.");
                }

                if (adults <= 0) {
                    const adultsInput = document.querySelector('input[name="adults"]');
                    addValidationError("adults", adultsInput, "Please select at least one adult.");
                }

                if (!guestName) {
                    const guestNameField = document.querySelector("#guest-name");
                    addValidationError("guest_name", guestNameField, "Please enter your name.");
                }

                if (!guestEmail) {
                    const guestEmailField = document.querySelector("#guest-email");
                    addValidationError("guest_email", guestEmailField, "Please enter your email.");
                } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(guestEmail)) {
                    const guestEmailField = document.querySelector("#guest-email");
                    addValidationError("guest_email", guestEmailField, "Please enter a valid email address.");
                }

                if (!phoneCountry) {
                    const phoneCountryInput = document.querySelector("#phone-country");
                    addValidationError("phone_country", phoneCountryInput, "Please select a country code.");
                }

                if (!phoneNumber) {
                    const phoneNumberInput = document.querySelector("#phone-number");
                    addValidationError("phone_number", phoneNumberInput, "Please enter your phone number.");
                }

                if ((userRole === "admin" || userRole === "representative") && partialPayment && parseFloat(partialPayment) > 0 && !partialPaidMethod) {
                    const partialPaidMethodField = document.querySelector("#partial-paid-method");
                    addValidationError("partial_paid_method", partialPaidMethodField, "Please select a payment method for partial payment.");
                }

                if (errors.length > 0) {
                    submitButton.disabled = false;
                    loadingSpinner.classList.add("hidden");
                    submitText.textContent = "Book Now";
                    return;
                }

                const formData = new FormData(bookingForm);
                formData.append("selected_date", selectedDate);
                formData.append("availability_id", availabilityId);
                formData.append("regions", regionId);
                formData.append("pickup_point", pickupPointId);
                formData.append("voucher_code", voucherCode || "");
                formData.append("partial_payment", partialPayment || "");
                formData.append("partial_paid_method", partialPaidMethod || "");

                fetch(window.location.href, {
                    method: "POST",
                    body: formData,
                    headers: {
                        "X-Requested-With": "XMLHttpRequest"
                    }
                })
                    .then((response) => {
                        if (!response.ok) {
                            throw new Error("Network response was not ok");
                        }
                        return response.json();
                    })
                    .then((data) => {
                        console.log("Response data:", data);

                        if (data.success) {
                            console.log("Redirecting to:", data.redirect_url);
                            window.location.href = data.redirect_url;
                        } else {
                            submitButton.disabled = false;
                            loadingSpinner.classList.add("hidden");
                            submitText.textContent = "Book Now";

                            const fieldSelectors = {
                                regions: "#regions",
                                pickup_point: "#pickup-point",
                                date: "#date-picker",
                                guest_name: "#guest-name",
                                guest_email: "#guest-email",
                                phone_country: "#phone-country",
                                phone_number: "#phone-number",
                                adults: 'input[name="adults"]',
                                children: 'input[name="children"]',
                                infants: 'input[name="infants"]',
                                partial_paid_method: "#partial-paid-method"
                            };

                            if (data.errors) {
                                Object.keys(data.errors).forEach((field) => {
                                    const selector = fieldSelectors[field] || `[name="${field}"]`;
                                    const input = document.querySelector(selector);

                                    if (input) {
                                        const errorText = Array.isArray(data.errors[field]) ? data.errors[field][0] : data.errors[field];
                                        showInlineError(input, errorText);
                                    }
                                });
                            }

                            if (data.message && formErrors) {
                                formErrors.classList.remove("hidden");
                                const errorList = formErrors.querySelector("ul");
                                if (errorList) {
                                    errorList.innerHTML = "";
                                    const errorItem = document.createElement("li");
                                    errorItem.textContent = data.message;
                                    errorList.appendChild(errorItem);
                                }
                            }
                        }
                    })
                    .catch((error) => {
                        console.error("Error:", error);

                        submitButton.disabled = false;
                        loadingSpinner.classList.add("hidden");
                        submitText.textContent = "Book Now";

                        if (formErrors) {
                            formErrors.classList.remove("hidden");
                            const errorList = formErrors.querySelector("ul");
                            if (errorList) {
                                errorList.innerHTML = "";
                                const errorItem = document.createElement("li");
                                errorItem.textContent = "An error occurred while processing your booking. Please try again.";
                                errorList.appendChild(errorItem);
                            }
                        }
                        console.log("error.message:", error.message);
                    });
            });
        }
    }

    initDeleteExcursion();
    initBookingForm();
    initGalleryLightbox();
}

document.addEventListener("DOMContentLoaded", initExcursionDetailPage);
