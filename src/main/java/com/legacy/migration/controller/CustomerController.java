package com.legacy.migration.controller;

import com.legacy.migration.model.Customer;
import com.legacy.migration.service.CustomerService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@Api(tags = "Customer Management API")
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService customerService;

    public CustomerController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @ApiOperation(value = "Get all customers")
    @RequestMapping(method = RequestMethod.GET)
    public List<Customer> getAllCustomers() {
        return customerService.getAllCustomers();
    }

    @ApiOperation(value = "Get customer by ID")
    @RequestMapping(value = "/{id}", method = RequestMethod.GET)
    public ResponseEntity<Customer> getCustomerById(
            @PathVariable("id") Long id) {

        Customer customer = customerService.getCustomerById(id);

        if (customer == null) {
            return new ResponseEntity<Customer>(HttpStatus.NOT_FOUND);
        }

        return new ResponseEntity<Customer>(customer, HttpStatus.OK);
    }

    @ApiOperation(value = "Create a customer")
    @RequestMapping(method = RequestMethod.POST)
    public ResponseEntity<Customer> createCustomer(
            @RequestBody Customer customer) {

        Customer createdCustomer =
                customerService.createCustomer(customer);

        return new ResponseEntity<Customer>(
                createdCustomer,
                HttpStatus.CREATED
        );
    }
}